"""Chapter-level orchestration: plan -> execute -> aggregate -> consistency pass.

This is the chapter-level main path. It reuses the existing segment-level
translation engine (segmenter, translator, schema) as its execution layer.

Batch 2 extends this with:
- RunManifest-based execution with persistent progress tracking
- Segment-level failure isolation (one failure does not abort the chapter)
- Resume capability (interrupted runs can continue from saved progress)
- Conservative retry / downgrade discipline (bounded, no infinite loops)

Batch 3 extends this with:
- Chapter-level consistency audit after aggregation
- Limited, conservative correction pass for term unification
- Final output path: plan -> execute -> aggregate -> consistency pass
"""

from __future__ import annotations

import json
import logging
import time
from typing import Callable, Dict, List, Optional, Tuple

from app.chapter.consistency import (
    build_consistency_reference,
    run_consistency_pass,
)
from app.chapter.manifest import (
    ChapterStatus,
    ResumeConfig,
    RunManifest,
    SegmentRecord,
    SegmentStatus,
)
from app.segment.segmenter import (
    create_segments,
    resolve_granularity_targets,
    Segment,
)
from app.translate.schema import GlossaryTerm, TranslationInput, TranslationOutput
from app.translate.translator import (
    AssetsMode,
    BudgetConfig,
    BUDGET_PROFILES,
    DEFAULT_ASSETS_MODE,
    build_translation_input,
    mock_glossary,
    polish_translation,
    resolve_budget_config,
    translate_draft,
)
from app.book_memory.retrieval import build_context_pack
from app.chapter.models import ChapterPlan, ChapterResult
from app.chapter.strategy import (
    assess_chapter_complexity,
    assess_segment_risks,
    build_strategy_plan,
)

logger = logging.getLogger(__name__)


def extract_chapter_title(source_text: str) -> str:
    """Extract the chapter title from the first non-empty line."""
    for line in source_text.splitlines():
        stripped = line.strip()
        if stripped:
            return stripped
    return "Untitled Chapter"


def format_aggregated_translation(
    chapter_title: str,
    segment_results: List[TranslationOutput],
) -> str:
    """Concatenate polished translations into a flowing full chapter.

    Output format contract (Batch 5A — chapter Markdown final output)
    -----------------------------------------------------------------
    The aggregated chapter Markdown returned by this function, and the
    ``final_translation`` derived from it (post-consistency-pass when
    available), must satisfy the following minimum rules:

    1. The orchestrator MUST NOT prepend the source-derived
       ``chapter_title`` (which is the raw first line of the source — for
       Chinese source novels this is Chinese, e.g. ``"第一章"``) as a
       heading on the aggregated output. The chapter heading visible in
       the final Markdown is whatever the segment-level translator
       produced inside segment 1.
    2. The first non-empty line of the final visible output MUST NOT
       contain CJK characters from the source title. Specifically: the
       raw ``chapter_title`` literal must not appear as the first line
       (with or without a leading ``#``).
    3. The raw Chinese ``chapter_title`` is metadata only. It is allowed
       to live in ``ChapterPlan.chapter_title``, ``ChapterResult.
       chapter_title``, manifest records, and source-bookkeeping logs;
       it must not surface as visible Markdown.
    4. Heading shape (``# Title`` vs plain English first line) is the
       segment-level translator's responsibility, not the orchestrator's.
       The orchestrator does not enforce a particular Markdown level.
    5. Segment polished outputs are joined in segment_id order with a
       blank line between sections. Empty polished outputs are skipped.

    Cross-module enforcement of this contract:

    * ``app.chapter.quality.validate_chapter_output`` enforces rule 2 via
      the ``title_untranslated`` and ``cjk_residue`` quality gates.
    * ``app.chapter.consistency.ChapterConsistencyAuditor._check_title_
      format`` enforces rule 1 (raw source-title leak) at audit time and
      MUST NOT propose corrections that would re-introduce the source
      ``chapter_title`` into the visible output.

    These three modules must agree on this contract; if you change the
    rule set here, update the consistency audit and quality gate in the
    same change.
    """
    parts = []
    for out in segment_results:
        text = out.polished_translation.strip()
        if text:
            parts.append(text)
            parts.append("")
    return "\n".join(parts).strip()


class ChapterOrchestrator:
    """Orchestrates chapter-level translation.

    Three phases:
      1. Planning  - segment full chapter text into executable units
      2. Execution - translate each segment via the existing engine
      3. Aggregation - combine segment results into a complete chapter output

    Batch 3 adds a fourth phase:
      4. Consistency pass - audit + limited correction on the aggregated output

    Each phase is a separate method so callers can inspect intermediate state.
    ``run()`` composes all three into a single call.

    Batch 2 additions:
    - ``run_with_manifest()`` — resilient execution with progress persistence
    - ``resume()`` — continue an interrupted run from its saved manifest

    Batch 3 additions:
    - ``_apply_consistency_pass()`` — audit + correction after aggregation
    - ``run_with_manifest()`` now includes the consistency pass in its output
    """

    def plan(self, source_text: str) -> ChapterPlan:
        """Phase 1: Produce a segment execution plan from raw chapter text.

        Batch 4A addition: after segmenting, runs pre-execution strategy
        assessment (chapter complexity, segment risks, strategy decisions).
        Strategy assessment failures are non-fatal — the plan still returns
        with a basic (non-strategy) plan.

        Batch 4B addition: strategy's ``segmentation_granularity`` decision
        now affects actual segmentation. If "finer" is recommended, segments
        are re-created with tighter size targets (800/500), and per-segment
        risk data is re-assessed so that segments, segment_risks, and
        segment_strategies all refer to the same actual segmentation.
        """
        chapter_title = extract_chapter_title(source_text)
        segments = create_segments(source_text)
        logger.info("Chapter plan: %d segments (initial), title=%r", len(segments), chapter_title)

        # Batch 4A: pre-execution strategy assessment
        try:
            reference = build_consistency_reference()
            complexity = assess_chapter_complexity(source_text, segments, reference)
            segment_risks = assess_segment_risks(segments, reference)
            strategy = build_strategy_plan(complexity, segment_risks)

            granularity = strategy.overall_strategy.segmentation_granularity

            # Batch 4B: apply granularity decision, then re-assess per-segment
            # data so the final plan is internally consistent.
            if granularity == "finer":
                max_chars, min_chars = resolve_granularity_targets("finer")
                segments = create_segments(source_text, max_chars=max_chars, min_chars=min_chars)
                segment_risks = assess_segment_risks(segments, reference)
                strategy = build_strategy_plan(complexity, segment_risks)
                logger.info(
                    "Applied FINER granularity: %d segments (max_chars=%d, min_chars=%d)",
                    len(segments), max_chars, min_chars,
                )

            logger.info(
                "Strategy assessment: complexity=%s, %d segments, "
                "high-risk=%d, granularity=%s",
                complexity.level.value,
                len(segment_risks),
                sum(1 for r in segment_risks.values() if r.risk_level.value == "high"),
                granularity,
            )

            return ChapterPlan(
                chapter_title=chapter_title,
                source_text=source_text,
                segments=segments,
                complexity_level=complexity.level.value,
                complexity_signals=strategy.chapter_complexity.signals.__dict__,
                segment_risks={
                    str(sid): {
                        "risk_level": sr.risk_level.value,
                        "score": sr.score,
                        "factors": sr.factors,
                    }
                    for sid, sr in strategy.segment_risks.items()
                },
                strategy_plan={
                    "complexity": {
                        "level": strategy.chapter_complexity.level.value,
                        "score": strategy.chapter_complexity.score,
                    },
                    "overall_strategy": {
                        "processing_mode": strategy.overall_strategy.processing_mode.value,
                        "budget_profile": strategy.overall_strategy.budget_profile.value,
                        "consistency_intensity": strategy.overall_strategy.consistency_intensity.value,
                        "segmentation_granularity": strategy.overall_strategy.segmentation_granularity,
                    },
                    "segment_strategies": {
                        str(sid): {
                            "risk_level": strategy.segment_risks[sid].risk_level.value,
                            "processing_mode": ss.processing_mode.value,
                            "budget_profile": ss.budget_profile.value,
                            "consistency_intensity": ss.consistency_intensity.value,
                        }
                        for sid, ss in strategy.segment_strategies.items()
                    },
                    "rationale": strategy.rationale,
                },
            )
        except Exception:
            logger.warning(
                "Strategy assessment failed; falling back to basic plan.",
                exc_info=True,
            )
            return ChapterPlan(
                chapter_title=chapter_title,
                source_text=source_text,
                segments=segments,
            )

    def execute(
        self,
        plan: ChapterPlan,
        glossary: Optional[List[GlossaryTerm]] = None,
        translate_draft_fn: Optional[Callable[[TranslationInput], TranslationOutput]] = None,
        assets_mode: AssetsMode = DEFAULT_ASSETS_MODE,
        model_profile: Optional["ModelProfile"] = None,
        book_memory: Optional["BookMemory"] = None,
    ) -> ChapterResult:
        """Phase 2 + 3: Execute each segment, then aggregate results.

        Each segment goes through the default workflow (draft -> review -> polish).
        ``translate_draft_fn`` lets callers inject a service-client or override
        for testing; when omitted the local ``translate_draft`` is used.

        When ``model_profile`` is provided, both review and polish passes use
        the profile's adapter path instead of ``MODEL_BACKEND_URL``.

        Batch 4B: resolves budget_config from plan's strategy_plan and passes
        it to translation functions. Builds an enactment record.

        Returns a ChapterResult with per-segment outputs and the full aggregated
        translation string.

        Note: This is the simple Batch 1 path. For manifest-based execution with
        failure isolation and resume, use ``run_with_manifest()`` instead.
        """
        if glossary is None:
            glossary = mock_glossary()

        # Batch 4B: resolve budget config from strategy plan
        budget_config = self._resolve_budget_from_plan(plan)

        segment_results: List[TranslationOutput] = []

        # R4 observability: context pack activation status
        if book_memory is not None:
            logger.info(
                "Context pack enabled — book_memory: %r (%d entities, %d titles)",
                book_memory.book_title,
                len(book_memory.entities),
                len(book_memory.titles),
            )

        for seg in plan.segments:
            # Build context pack from book memory if available (R3)
            context_pack_text = ""
            if book_memory is not None:
                pack = build_context_pack(seg.text, book_memory)
                context_pack_text = pack.format_text()
                logger.info(
                    "  Segment %s: context pack %d chars (truncated=%s, empty=%s)",
                    seg.segment_id, len(context_pack_text), pack.truncated, pack.is_empty,
                )
            inp = build_translation_input(seg, glossary, context_pack_text=context_pack_text)
            logger.info("  Translating segment %s ...", inp.segment_id)

            if translate_draft_fn is not None:
                draft_out = translate_draft_fn(inp)
            else:
                draft_out = translate_draft(inp, assets_mode=assets_mode, budget_config=budget_config)

            final_out = polish_translation(inp, draft_out, assets_mode=assets_mode, budget_config=budget_config, model_profile=model_profile)
            segment_results.append(final_out)

        aggregated = format_aggregated_translation(
            plan.chapter_title, segment_results,
        )

        result = ChapterResult(
            chapter_title=plan.chapter_title,
            source_text=plan.source_text,
            segment_results=segment_results,
            aggregated_translation=aggregated,
            strategy_plan_summary=plan.strategy_plan,
        )
        # Batch 4B: attach enactment record
        result.enactment = self._build_enactment(plan, budget_config, self._resolve_consistency_intensity_from_plan(plan), None, len(plan.segments))
        # Quality gates: populate report so manifest completion ≠ quality pass.
        from app.chapter.quality import validate_chapter_output
        result.quality_report = validate_chapter_output(result)
        return result

    def run(
        self,
        source_text: str,
        glossary: Optional[List[GlossaryTerm]] = None,
        translate_draft_fn: Optional[Callable[[TranslationInput], TranslationOutput]] = None,
        assets_mode: AssetsMode = DEFAULT_ASSETS_MODE,
        model_profile: Optional["ModelProfile"] = None,
        book_memory: Optional["BookMemory"] = None,
    ) -> ChapterResult:
        """Full chapter pipeline: plan -> execute -> aggregate.

        This is the single entry point for translating a full chapter.

        For resilient execution with progress persistence, failure isolation,
        and resume support, use ``run_with_manifest()`` instead.
        """
        plan = self.plan(source_text)
        result = self.execute(
            plan,
            glossary=glossary,
            translate_draft_fn=translate_draft_fn,
            assets_mode=assets_mode,
            model_profile=model_profile,
            book_memory=book_memory,
        )
        return result

    # ── Batch 2: Manifest-based execution ───────────────────────────────

    def run_with_manifest(
        self,
        source_text: str,
        glossary: Optional[List[GlossaryTerm]] = None,
        translate_draft_fn: Optional[Callable[[TranslationInput], TranslationOutput]] = None,
        assets_mode: AssetsMode = DEFAULT_ASSETS_MODE,
        resume_config: Optional[ResumeConfig] = None,
        manifest_path: Optional[str] = None,
        existing_manifest: Optional[RunManifest] = None,
        book_memory: Optional["BookMemory"] = None,
        smoke_test: bool = False,
        model_profile: Optional["ModelProfile"] = None,
    ) -> ChapterResult:
        """Resilient chapter pipeline with manifest-based progress tracking.

        Unlike ``run()``, this method:
        1. Creates (or reuses) a RunManifest to track progress
        2. Isolates segment failures — one failed segment does not abort
           the entire chapter
        3. Persists progress after each segment
        4. Supports resume: pass ``existing_manifest`` to continue from
           saved progress

        Batch 4B: resolves budget_config and consistency_intensity from plan's
        strategy_plan, passes them to translation and consistency functions,
        and builds an enactment record.

        Args:
            source_text: Full chapter source text.
            glossary: Glossary terms (defaults to mock glossary).
            translate_draft_fn: Override for the draft translation function.
            assets_mode: Asset injection mode ("full" or "none").
            resume_config: Retry/downgrade bounds (defaults if omitted).
            manifest_path: Where to persist the manifest. Derived from
                output path if not provided.
            existing_manifest: When provided, resume from this manifest
                instead of starting fresh.
            smoke_test: When True, skip consistency pass and quality gate.
                Output is mock translation — not a real translation.

        Returns:
            ChapterResult with runtime status (chapter_status, segment_statuses,
            failed_segment_ids, resumable, manifest).
        """
        if glossary is None:
            glossary = mock_glossary()

        plan = self.plan(source_text)
        resume_config = resume_config or ResumeConfig()

        # Batch 4B: resolve budget config and consistency intensity from strategy plan
        budget_config = self._resolve_budget_from_plan(plan)
        consistency_intensity = self._resolve_consistency_intensity_from_plan(plan)

        # Determine which segments to run and which to skip.
        if existing_manifest is not None:
            manifest = existing_manifest
            segment_ids_to_run = manifest.get_pending_segment_ids()
            if manifest.total_segments != plan.segment_count:
                logger.warning(
                    "Segment count mismatch: manifest has %d, plan has %d. "
                    "Resuming with manifest's segment set.",
                    manifest.total_segments, plan.segment_count,
                )
        else:
            segment_ids = [str(s.segment_id) for s in plan.segments]
            manifest = RunManifest.create(
                chapter_title=plan.chapter_title,
                source_text=source_text,
                segment_ids=segment_ids,
                resume_config=resume_config,
                manifest_path=manifest_path,
                smoke_test=smoke_test,
            )
            segment_ids_to_run = list(segment_ids)

        manifest.start_run()
        if manifest.manifest_path:
            manifest.save()

        # Build a lookup from segment_id to Segment object.
        seg_map: Dict[str, Segment] = {
            str(s.segment_id): s for s in plan.segments
        }

        # Collect actual segment results during execution.
        segment_results: Dict[str, TranslationOutput] = {}

        # R4 observability: context pack activation status
        if book_memory is not None:
            logger.info(
                "Context pack enabled — book_memory: %r (%d entities, %d titles)",
                book_memory.book_title,
                len(book_memory.entities),
                len(book_memory.titles),
            )

        # Execute pending/retryable segments.
        for seg_id in segment_ids_to_run:
            seg = seg_map.get(seg_id)
            if seg is None:
                logger.warning("Segment %s not found in plan; skipping.", seg_id)
                continue

            # Build context pack from book memory if available (R3)
            context_pack_text = ""
            if book_memory is not None:
                pack = build_context_pack(seg.text, book_memory)
                context_pack_text = pack.format_text()
                logger.info(
                    "  Segment %s: context pack %d chars (truncated=%s, empty=%s)",
                    seg_id, len(context_pack_text), pack.truncated, pack.is_empty,
                )

            result = self._execute_segment_with_retry(
                seg=seg,
                glossary=glossary,
                translate_draft_fn=translate_draft_fn,
                assets_mode=assets_mode,
                budget_config=budget_config,
                manifest=manifest,
                resume_config=resume_config,
                model_profile=model_profile,
                context_pack_text=context_pack_text,
            )

            if result is not None:
                segment_results[seg_id] = result

            if manifest.manifest_path:
                manifest.save()

        manifest.complete_run()
        if manifest.manifest_path:
            manifest.save()

        # Aggregate: include completed segments (newly done + previously done on resume).
        completed_ids = manifest.get_completed_segment_ids()
        ordered_results: List[TranslationOutput] = []
        for seg in plan.segments:
            sid = str(seg.segment_id)
            if sid in segment_results:
                ordered_results.append(segment_results[sid])
            elif sid in completed_ids:
                # Reconstruct the TranslationOutput from manifest-stored
                # polished text so the quality gate sees actual output,
                # not an empty stub.
                rec = manifest.segments.get(sid)
                polished = rec.polished_text if rec else ""
                ordered_results.append(
                    TranslationOutput(
                        segment_id=sid,
                        draft_translation="",
                        polished_translation=polished,
                    )
                )

        aggregated = format_aggregated_translation(
            plan.chapter_title, ordered_results,
        )

        failed_ids = [
            sid for sid, rec in manifest.segments.items()
            if rec.status == SegmentStatus.FAILED
        ]

        # Batch 3: consistency pass on the aggregated output.
        # Skipped in smoke-test mode (output is mock, not real translation).
        if smoke_test:
            audit_summary, correction_summary, corrected_text = None, None, None
        else:
            audit_summary, correction_summary, corrected_text = self._apply_consistency_pass(
                aggregated_text=aggregated,
                chapter_title=plan.chapter_title,
                ordered_results=ordered_results,
                consistency_intensity=consistency_intensity,
            )

        result = ChapterResult(
            chapter_title=plan.chapter_title,
            source_text=plan.source_text,
            segment_results=ordered_results,
            aggregated_translation=aggregated,
            chapter_status=manifest.status,
            segment_statuses={
                sid: rec.status for sid, rec in manifest.segments.items()
            },
            manifest=manifest,
            failed_segment_ids=failed_ids,
            resumable=manifest.is_resumable(),
            # Batch 3 consistency fields
            consistency_audit=audit_summary,
            correction_summary=correction_summary,
            corrected_translation=corrected_text,
            # Batch 4A strategy visibility
            strategy_plan_summary=plan.strategy_plan,
            smoke_test=smoke_test,
        )
        seg_granularity = (
            plan.strategy_plan.get("overall_strategy", {}).get("segmentation_granularity")
            if plan.strategy_plan else None
        )
        result.enactment = self._build_enactment(
            plan=plan,
            budget_config=budget_config,
            consistency_intensity=consistency_intensity,
            segmentation_granularity=seg_granularity,
            segment_count=len(plan.segments),
        )
        if not smoke_test:
            from app.chapter.quality import validate_chapter_output
            result.quality_report = validate_chapter_output(result)
            # Persist the quality summary into the manifest so the manifest
            # cannot say "completed" while the quality gate failed.
            manifest.quality_summary = result.quality_report.to_summary()
            # Demote status on quality failure so "COMPLETED" is honest.
            if not result.quality_report.passed:
                result.chapter_status = ChapterStatus.PARTIAL
                manifest.status = ChapterStatus.PARTIAL
        else:
            # Smoke-test runs do not produce real translations, so the quality
            # gate is not meaningful. Record the mode in the manifest so a
            # "completed" smoke manifest cannot pass as a normal quality pass.
            manifest.quality_summary = {"smoke_test": True, "passed": False}
        if manifest.manifest_path:
            manifest.save()
        return result

    def _execute_segment_with_retry(
        self,
        seg: Segment,
        glossary: List[GlossaryTerm],
        translate_draft_fn: Optional[Callable[[TranslationInput], TranslationOutput]],
        assets_mode: AssetsMode,
        budget_config: BudgetConfig,
        manifest: RunManifest,
        resume_config: ResumeConfig,
        model_profile: Optional["ModelProfile"] = None,
        context_pack_text: str = "",
    ) -> Optional[TranslationOutput]:
        """Execute a single segment with retry discipline.

        When ``model_profile`` is provided, review and polish passes use
        the profile's adapter path instead of ``MODEL_BACKEND_URL``.

        Returns the TranslationOutput on success, None if all retries failed.
        Updates the manifest with each attempt.
        """
        seg_id = str(seg.segment_id)
        logger.info("  Segment %s starting...", seg_id)
        inp = build_translation_input(seg, glossary, context_pack_text=context_pack_text)
        manifest.mark_segment_running(seg_id)

        for attempt in range(1 + resume_config.max_retries):
            if attempt > 0:
                logger.info(
                    "  Retrying segment %s (attempt %d/%d) ...",
                    seg_id, attempt, resume_config.max_retries,
                )
                manifest.segments[seg_id].retry_count = attempt
                if resume_config.retry_delay_seconds > 0:
                    time.sleep(resume_config.retry_delay_seconds)

            try:
                if translate_draft_fn is not None:
                    draft_out = translate_draft_fn(inp)
                else:
                    draft_out = translate_draft(inp, assets_mode=assets_mode, budget_config=budget_config)

                final_out = polish_translation(inp, draft_out, assets_mode=assets_mode, budget_config=budget_config, model_profile=model_profile)
                manifest.segments[seg_id].polished_text = final_out.polished_translation or ""
                manifest.mark_segment_completed(seg_id)
                logger.info("  Segment %s completed.", seg_id)
                return final_out

            except Exception as e:
                error_msg = f"{type(e).__name__}: {e}"
                logger.warning(
                    "  Segment %s failed (attempt %d/%d): %s",
                    seg_id, attempt + 1, resume_config.max_retries + 1, error_msg,
                )
                if attempt < resume_config.max_retries:
                    continue
                manifest.mark_segment_failed(seg_id, error_msg)
                logger.error(
                    "  Segment %s failed after %d attempts. Marking as failed.",
                    seg_id, resume_config.max_retries + 1,
                )
                return None

        return None

    # ── Batch 3: Consistency pass ───────────────────────────────────────

    def _build_segment_texts(
        self, ordered_results: List[TranslationOutput]
    ) -> List[Tuple[str, str]]:
        """Build list of (segment_id, polished_text) from ordered results.

        Filters out empty results (e.g. placeholder entries from resume
        where the TranslationOutput was not available in memory).
        """
        return [
            (r.segment_id, r.polished_translation)
            for r in ordered_results
            if r.polished_translation.strip()
        ]

    def _apply_consistency_pass(
        self,
        aggregated_text: str,
        chapter_title: str,
        ordered_results: List[TranslationOutput],
        consistency_intensity: str = "standard",
    ) -> Tuple[Optional[dict], Optional[dict], Optional[str]]:
        """Run the Batch 3 consistency pass on the aggregated chapter output.

        This is intentionally lightweight: it builds reference data from
        project assets, runs the audit, applies limited corrections, and
        returns structured summaries. It does NOT rewrite prose or run
        additional model calls.

        Returns:
            (audit_summary_dict, correction_summary_dict, corrected_text_or_None)
        """
        segment_texts = self._build_segment_texts(ordered_results)
        if not segment_texts:
            logger.info("No segment texts available; skipping consistency pass.")
            return None, None, None

        try:
            reference = build_consistency_reference()
            corrected_text, audit, correction = run_consistency_pass(
                aggregated_text=aggregated_text,
                chapter_title=chapter_title,
                segment_texts=segment_texts,
                reference=reference,
                intensity=consistency_intensity,
            )
            audit_summary = audit.get_summary()
            correction_summary = correction.get_summary()

            if audit_summary["total_issues"] > 0:
                logger.info(
                    "Consistency audit: %d issues found (%d auto-fixable, %d auto-fixed).",
                    audit_summary["total_issues"],
                    audit_summary["auto_fixable"],
                    audit_summary["auto_fixed"],
                )
                for cat, count in audit_summary["by_category"].items():
                    logger.info("  %s: %d", cat, count)

            if correction_summary["total_corrections"] > 0:
                logger.info(
                    "Consistency corrections: %d action(s), %d replacement(s).",
                    correction_summary["total_corrections"],
                    correction_summary["total_replacements"],
                )

            corrected = corrected_text if correction.has_corrections else None
            return audit_summary, correction_summary, corrected

        except Exception as e:
            logger.warning(
                "Consistency pass failed: %s. Continuing with uncorrected output.",
                e,
            )
            return None, None, None

    # ── Batch 4B: Strategy enactment helpers ─────────────────────────────

    def _resolve_budget_from_plan(self, plan: ChapterPlan) -> BudgetConfig:
        """Resolve budget configuration from the plan's strategy_plan.

        Falls back to standard budget profile if strategy_plan is missing.
        """
        if plan.strategy_plan is None:
            return resolve_budget_config("standard")

        overall = plan.strategy_plan.get("overall_strategy", {})
        profile = overall.get("budget_profile", "standard")
        return resolve_budget_config(profile)

    def _resolve_consistency_intensity_from_plan(self, plan: ChapterPlan) -> str:
        """Resolve consistency intensity from the plan's strategy_plan.

        Falls back to "standard" if strategy_plan is missing.
        """
        if plan.strategy_plan is None:
            return "standard"

        overall = plan.strategy_plan.get("overall_strategy", {})
        return overall.get("consistency_intensity", "standard")

    def _build_enactment(
        self,
        plan: ChapterPlan,
        budget_config: BudgetConfig,
        consistency_intensity: Optional[str],
        segmentation_granularity: Optional[str],
        segment_count: Optional[int],
    ) -> Optional[dict]:
        """Build an enactment record showing how strategy decisions were applied.

        Returns None when strategy_plan is missing (no strategy assessment).
        Only records values that are explicitly known; unknown values are None.
        """
        if plan.strategy_plan is None:
            return None

        overall = plan.strategy_plan.get("overall_strategy", {})
        planned_granularity = overall.get("segmentation_granularity")
        planned_budget = overall.get("budget_profile")
        planned_consistency = overall.get("consistency_intensity")

        # Map budget_config to profile name if possible
        budget_profile = None
        if budget_config is not None:
            # Try to find matching profile
            for name, config in BUDGET_PROFILES.items():
                if (config.draft_max_tokens == budget_config.draft_max_tokens and
                    config.review_max_tokens == budget_config.review_max_tokens and
                    config.polish_max_tokens == budget_config.polish_max_tokens):
                    budget_profile = name
                    break

        return {
            "planned": {
                "segmentation_granularity": planned_granularity,
                "budget_profile": planned_budget,
                "consistency_intensity": planned_consistency,
            },
            "enacted": {
                "segmentation": {
                    "granularity": segmentation_granularity,
                    "max_chars": None,  # Not known without segmenter context
                    "min_chars": None,
                    "segment_count": segment_count,
                },
                "budget": {
                    "profile": budget_profile,
                    "draft_max_tokens": budget_config.draft_max_tokens if budget_config else None,
                    "review_max_tokens": budget_config.review_max_tokens if budget_config else None,
                    "polish_max_tokens": budget_config.polish_max_tokens if budget_config else None,
                },
                "consistency": {
                    "intensity": consistency_intensity,
                    "audit_issues_found": None,  # Not available at this point
                    "auto_fixable": None,
                    "auto_fixed": None,
                    "corrections_applied": None,
                }
            },
            "consistent": None,  # Cannot determine without more context
        }

    # ── Resume ──────────────────────────────────────────────────────────

    @staticmethod
    def load_manifest(manifest_path: str) -> Optional[RunManifest]:
        """Load a manifest from disk.

        Returns None if the file does not exist or is unreadable.
        """
        try:
            return RunManifest.load(manifest_path)
        except (FileNotFoundError, json.JSONDecodeError, KeyError) as e:
            logger.warning("Could not load manifest from %s: %s", manifest_path, e)
            return None

    def resume(
        self,
        source_text: str,
        manifest_path: str,
        glossary: Optional[List[GlossaryTerm]] = None,
        translate_draft_fn: Optional[Callable[[TranslationInput], TranslationOutput]] = None,
        assets_mode: AssetsMode = DEFAULT_ASSETS_MODE,
        model_profile: Optional["ModelProfile"] = None,
        book_memory: Optional["BookMemory"] = None,
    ) -> Optional[ChapterResult]:
        """Resume an interrupted chapter run from its saved manifest.

        Args:
            source_text: Full chapter source text (used for re-planning).
            manifest_path: Path to the saved manifest JSON file.
            glossary: Glossary terms.
            translate_draft_fn: Override for the draft translation function.
            assets_mode: Asset injection mode.
            model_profile: When provided, review and polish passes use
                the profile's adapter path instead of ``MODEL_BACKEND_URL``.
            book_memory: When provided, context packs are built from book
                memory for pending / retried segments (R3/R4).

        Returns:
            ChapterResult if the manifest was loaded and run continued,
            None if the manifest could not be loaded or is not resumable.
        """
        manifest = self.load_manifest(manifest_path)
        if manifest is None:
            logger.error("Cannot resume: manifest not found at %s", manifest_path)
            return None

        if not manifest.is_resumable():
            logger.info(
                "Manifest %s is not resumable (status=%s). "
                "Chapter is already complete or in a terminal state.",
                manifest.run_id, manifest.status.value,
            )
            return None

        logger.info(
            "Resuming run %s for chapter %r (%d/%d segments completed, "
            "%d pending, %d failed)%s",
            manifest.run_id,
            manifest.chapter_title,
            len(manifest.get_completed_segment_ids()),
            manifest.total_segments,
            len(manifest.get_pending_segment_ids()),
            sum(1 for r in manifest.segments.values() if r.status == SegmentStatus.FAILED),
            " with book_memory" if book_memory is not None else "",
        )

        return self.run_with_manifest(
            source_text=source_text,
            glossary=glossary,
            translate_draft_fn=translate_draft_fn,
            assets_mode=assets_mode,
            existing_manifest=manifest,
            manifest_path=manifest_path,
            smoke_test=manifest.smoke_test,
            model_profile=model_profile,
            book_memory=book_memory,
        )
