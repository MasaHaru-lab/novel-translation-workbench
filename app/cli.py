#!/usr/bin/env python3
"""
CLI for novel translation workbench.
"""
import argparse
import logging
import sys
import time
from contextlib import contextmanager
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, Iterator, List, Optional

from app.chapter.manifest import RunManifest, ResumeConfig
from app.chapter.orchestrator import ChapterOrchestrator
from app.chapter.models import ChapterResult
from app.config_loader import find_project_root
from app.chapter.validator import (
    ValidationResult,
    resolve_git_ref,
    validate_chapter_run,
)
from app.segment.segmenter import create_segments
from app.translate.translator import (
    ASSETS_MODES,
    DEFAULT_ASSETS_MODE,
    AssetsMode,
    _validate_assets_mode,
    build_translation_input,
    mock_glossary,
    polish_translation,
    set_smoke_mode,
    translate_draft,
)
from app.translate.schema import TranslationInput, TranslationOutput
from app.translate.backend_adapter import translate_draft_with_profile
from app.book_memory.serialization import book_memory_from_dict
from app.config import config


@contextmanager
def _orchestrator_progress_logging() -> Iterator[None]:
    """Temporarily show the orchestrator's per-segment progress on stdout."""
    log = logging.getLogger('app.chapter.orchestrator')
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(logging.Formatter('%(message)s'))
    prev_level = log.level
    log.setLevel(logging.INFO)
    log.addHandler(handler)
    try:
        yield
    finally:
        log.removeHandler(handler)
        handler.close()
        log.setLevel(prev_level)


def _resolve_source(source: Path) -> Path:
    """Resolve a source path with project-root-aware fallback.

    If the path exists as-is, return it unchanged. If it does not exist but
    resolves relative to the project root, return that instead. Otherwise
    return the original path so the caller can produce a clear diagnostic.
    """
    if source.exists():
        return source
    alt = find_project_root() / source
    if alt.exists():
        return alt
    return source


def _derive_output_path(source: Path) -> Path:
    """Derive a default output path from the source path.

    ``data/source/chapter3.txt`` becomes ``data/exports/chapter3_en.md``,
    resolved relative to the project root.
    """
    return find_project_root() / "data/exports" / f"{source.stem}_en.md"


def load_book_memory(path: Optional[Path]):
    """Load a BookMemory from a JSON file path, or return None.

    Args:
        path: Path to a JSON file serialized via ``book_memory_to_dict()``.

    Returns:
        A ``BookMemory`` instance, or ``None`` if path is None.
    """
    if path is None:
        return None
    import json
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        memory = book_memory_from_dict(data)
        logger = logging.getLogger(__name__)
        logger.info(
            "Loaded BookMemory from %s: %r (%d entities, %d titles)",
            path, memory.book_title, len(memory.entities), len(memory.titles),
        )
        return memory
    except Exception as e:
        logger = logging.getLogger(__name__)
        logger.error("Failed to load BookMemory from %s: %s", path, e)
        raise


def read_source_file(source_path: Path) -> str:
    """Read the source text file."""
    if not source_path.exists():
        raise FileNotFoundError(f"Source file not found: {source_path}")
    return source_path.read_text(encoding='utf-8')


def write_markdown(output_path: Path, segments, translation_outputs):
    """Write the markdown file with segments, drafts, polished translations, and notes."""
    with output_path.open('w', encoding='utf-8') as f:
        f.write("# Chapter 1\n\n")
        f.write("---\n\n")
        for seg, out in zip(segments, translation_outputs):
            f.write(f"## Segment {seg.segment_id}\n\n")
            f.write("### Draft\n")
            f.write(out.draft_translation + "\n\n")
            f.write("### Polished\n")
            f.write(out.polished_translation + "\n\n")
            if out.notes:
                f.write("### Notes\n")
                for note in out.notes:
                    f.write(f"- {note}\n")
                f.write("\n")
            f.write("---\n\n")


def run_pipeline(
    source_path: Path,
    output_path: Path,
    service_url: Optional[str] = None,
    allow_mock_fallback: bool = False,
    assets_mode: AssetsMode = DEFAULT_ASSETS_MODE,
    model_profile: Optional[str] = None,
):
    """Run the translation pipeline.

    ``assets_mode`` is threaded through to the translation-call layer. The
    default ("full") preserves existing behavior; the CLI exposes this via
    ``--assets-mode``. See ``translator.build_project_assets_block`` for
    semantics.
    """
    _validate_assets_mode(assets_mode)

    # Profile-based path takes priority
    if model_profile:
        from app.translate.model_profiles import get_profile, list_profiles
        from app.config_loader import load_env_local

        load_env_local()
        try:
            profile = get_profile(model_profile)
        except KeyError:
            known = list_profiles()
            print(f"  Error: Unknown model profile {model_profile!r}.")
            print(f"  Available profiles: {', '.join(sorted(known))}")
            sys.exit(1)

        def profile_fn(inp):
            return translate_draft_with_profile(inp, profile, assets_mode=assets_mode)

        print(f"Reading source from {source_path}")
        text = read_source_file(source_path)
        print(f"Loaded {len(text)} characters.")
        print("Segmenting text...")
        segments = create_segments(text)
        print(f"Created {len(segments)} segments.")
        print(f"Translating using profile: {model_profile}...")

        glossary = mock_glossary()
        translation_outputs = []
        for seg in segments:
            print(f"  Segment {seg.segment_id}...")
            inp = build_translation_input(seg, glossary)
            draft_out = profile_fn(inp)
            final_out = polish_translation(inp, draft_out, assets_mode=assets_mode)
            translation_outputs.append(final_out)
        print(f"Writing output to {output_path}")
        write_markdown(output_path, segments, translation_outputs)
        print("Done.")
        return

    print(f"Reading source from {source_path}")
    text = read_source_file(source_path)
    print(f"Loaded {len(text)} characters.")

    print("Segmenting text...")
    segments = create_segments(text)
    print(f"Created {len(segments)} segments.")

    glossary = mock_glossary()
    translation_outputs = []

    # Choose translation method
    http_translate_fn = None
    if service_url:
        print(f"Using translation service at {service_url}")
        # Try to import HTTP client
        try:
            from app.service.client import TranslationServiceClient
            # Create client with explicit base_url
            client = TranslationServiceClient(base_url=service_url)
            http_translate_fn = client.translate_draft
            print("  Service client imported successfully.")
        except Exception as e:
            print(f"  Warning: Could not import translation service client: {e}")
            if not allow_mock_fallback:
                print("  Falling back to local mock translation is not allowed (--allow-mock-fallback not set).")
                print(f"  Error: Service unavailable. Exiting.")
                sys.exit(1)
            else:
                print("  Falling back to local mock translation (--allow-mock-fallback enabled).")
                http_translate_fn = None

    # Local mock translation function. Wrap so assets_mode is threaded through
    # whenever the pipeline falls back to (or starts on) local translation.
    # HTTP service path intentionally keeps its existing single-arg contract.
    from app.translate.translator import translate_draft as local_translate_draft

    def local_translate_fn(inp):
        return local_translate_draft(inp, assets_mode=assets_mode)

    # Decide which function to use
    if service_url and http_translate_fn is not None:
        translate_draft_fn = http_translate_fn
        translation_mode = "service"
    else:
        translate_draft_fn = local_translate_fn
        translation_mode = "configured model backend" if config.MODEL_BACKEND_URL.strip() else "local (no backend)"

    print(f"Translating using {translation_mode}...")
    service_failed = False
    for seg in segments:
        print(f"  Segment {seg.segment_id}...")
        # Build structured input
        input = build_translation_input(seg, glossary)
        # Draft translation
        try:
            draft_out = translate_draft_fn(input)
        except Exception as e:
            if not allow_mock_fallback:
                print(f"  Error: Translation service call failed: {e}")
                print(f"  Service URL: {service_url}")
                print(f"  Falling back to local mock translation is not allowed (--allow-mock-fallback not set).")
                sys.exit(1)
            else:
                print(f"  Warning: Translation service call failed: {e}")
                print(f"  Service URL: {service_url}")
                print(f"  Falling back to local mock translation (--allow-mock-fallback enabled).")
                # Switch to local translation for this and subsequent segments
                translate_draft_fn = local_translate_fn
                translation_mode = "configured model backend" if config.MODEL_BACKEND_URL.strip() else "local (no backend)"
                service_failed = True
                # Retry with local translation
                draft_out = translate_draft_fn(input)
        # Polish translation (always local mock for now)
        final_out = polish_translation(input, draft_out, assets_mode=assets_mode)
        translation_outputs.append(final_out)

    print(f"Writing output to {output_path}")
    write_markdown(output_path, segments, translation_outputs)
    print("Done.")


def _resolve_translate_fn(
    service_url: Optional[str],
    allow_mock_fallback: bool,
    assets_mode: AssetsMode,
    model_profile: Optional[str] = None,
) -> tuple[Optional[Callable[[TranslationInput], TranslationOutput]], str]:
    """Resolve which translate function to use: service client, profile-based, or local.

    When ``model_profile`` is set, uses the profile-based adapter path.
    Otherwise falls through to the existing service/local resolution.

    Returns (translate_fn, mode_label).
    ``translate_fn`` is None when neither service, profile, nor local is available.
    """
    _validate_assets_mode(assets_mode)

    # Profile-based path takes priority when explicitly selected
    if model_profile:
        from app.translate.model_profiles import get_profile, list_profiles
        from app.config_loader import load_env_local

        load_env_local()

        try:
            profile = get_profile(model_profile)
        except KeyError:
            known = list_profiles()
            print(f"  Error: Unknown model profile {model_profile!r}.")
            print(f"  Available profiles: {', '.join(sorted(known))}")
            return None, "error"

        def profile_translate_fn(inp: TranslationInput) -> TranslationOutput:
            return translate_draft_with_profile(inp, profile, assets_mode=assets_mode)

        return profile_translate_fn, f"profile: {model_profile}"

    from app.translate.translator import translate_draft as local_translate_draft

    def local_fn(inp):
        return local_translate_draft(inp, assets_mode=assets_mode)

    http_fn = None
    if service_url:
        try:
            from app.service.client import TranslationServiceClient
            client = TranslationServiceClient(base_url=service_url)
            http_fn = client.translate_draft
        except Exception as e:
            print(f"  Warning: Could not import translation service client: {e}")
            if not allow_mock_fallback:
                print("  Service client unavailable. Use --allow-mock-fallback to fall back to local translation.")
                return None, "error"
            print("  Falling back to local mock translation (--allow-mock-fallback enabled).")

    if http_fn is not None:
        return http_fn, "service"
    if config.MODEL_BACKEND_URL.strip():
        return local_fn, "configured model backend"
    return local_fn, "local (no backend)"


def run_chapter_pipeline(
    source_path: Path,
    output_path: Path,
    service_url: Optional[str] = None,
    allow_mock_fallback: bool = False,
    assets_mode: AssetsMode = DEFAULT_ASSETS_MODE,
    model_profile: Optional[str] = None,
    resume: bool = False,
    dry_run: bool = False,
    max_retries: int = 2,
    retry_delay_seconds: float = 1.0,
    auto_retry_on_resume: bool = True,
    no_clobber: bool = False,
    confirm: bool = False,
    smoke_test: bool = False,
    book_memory_path: Optional[Path] = None,
):
    """Run the chapter-level translation pipeline.

    Reads a full chapter, auto-segments, auto-translates each segment,
    and aggregates into a complete chapter-level English output file.

    When ``resume=True``, attempts to load a saved run manifest for the
    output path and continue from where a previous run left off.
    When ``confirm=True``, shows the chapter plan and prompts for
    confirmation before executing.

    When ``smoke_test=True``, runs with deterministic mock translation
    (no real model backend required). Output is clearly labeled as
    smoke test — it is not a real translation. Quality gates and
    consistency passes are skipped.
    """
    _validate_assets_mode(assets_mode)
    # Validate resume configuration parameters
    if max_retries < 0:
        raise ValueError(f"max_retries must be >= 0, got {max_retries}")
    if retry_delay_seconds < 0:
        raise ValueError(f"retry_delay_seconds must be >= 0, got {retry_delay_seconds}")

    # Create ResumeConfig instance
    resume_config = ResumeConfig(
        max_retries=max_retries,
        retry_delay_seconds=retry_delay_seconds,
        auto_retry_on_resume=auto_retry_on_resume,
    )

    # ── Stage 4: Pre-run validation ──────────────────────────────────────
    vresult = validate_chapter_run(
        source_path=source_path,
        output_path=output_path,
        book_memory_path=book_memory_path,
        is_dry_run=dry_run,
        is_resume=resume,
    )
    for line in vresult.format_lines():
        print(line)
    if not vresult.passed:
        if any("not found" in e for e in vresult.errors):
            print(f"  Tip: Run from the project root ({find_project_root()}) or use an absolute --source path.")
        sys.exit(1)

    try:
        text = read_source_file(source_path)
    except FileNotFoundError as e:
        print(f"  Error: {e}")
        sys.exit(1)
    print(f"Loaded {len(text)} characters.")

    # ── No-clobber check ─────────────────────────────────────────────────
    if no_clobber and output_path.exists():
        print(f"  Error: Output file already exists: {output_path}")
        print(f"  Remove the file or use a different --output path.")
        sys.exit(1)

    # ── Plan preview (dry-run and/or confirm) ─────────────────────────────
    if dry_run or confirm:
        orchestrator = ChapterOrchestrator()
        plan = orchestrator.plan(text)
        _display_plan(plan)
        if confirm:
            ans = input("  Continue? [y/N] ").strip().lower()
            if ans not in ('y', 'yes'):
                print("  Aborted.")
                sys.exit(0)
        if dry_run and not confirm:
            return

    translate_fn, mode = _resolve_translate_fn(service_url, allow_mock_fallback, assets_mode, model_profile=model_profile)
    if translate_fn is None:
        print(f"  Error: Service unavailable. Exiting.")
        sys.exit(1)

    # Resolve the profile object for review/polish orchestration.
    profile_obj = None
    if model_profile:
        from app.translate.model_profiles import get_profile
        profile_obj = get_profile(model_profile)

    # Enable explicit smoke-test mode so the pipeline degrades visibly
    # rather than producing a false green.
    set_smoke_mode(smoke_test)

    manifest_path = RunManifest.default_manifest_path(str(output_path))
    orchestrator = ChapterOrchestrator()

    # ── Load BookMemory (if provided) ────────────────────────────────────
    book_memory = load_book_memory(book_memory_path)

    # ── Resume path ──────────────────────────────────────────────────────
    if resume:
        try:
            manifest = orchestrator.load_manifest(manifest_path)
        except Exception:
            manifest = None

        if manifest is not None:
            summary = manifest.get_summary()
            print(f"\nFound saved manifest for run {summary['run_id']}:")
            print(f"  Status:      {summary['status']}")
            print(f"  Completed:   {summary['completed']}/{summary['total_segments']} segments")
            print(f"  Failed:      {summary['failed']}")
            print(f"  Pending:     {summary['pending']}")
            if book_memory is not None:
                print(f"  BookMemory:  {book_memory.book_title!r} ({len(book_memory.entities)} entities)")
            print(f"  Manifest:    {manifest_path}")
            if summary['resumable']:
                completed = summary['completed']
                pending = summary['pending']
                failed = summary['failed']
                print(f"  → Completed segments ({completed}) will be reused.")
                if pending:
                    print(f"  → Pending segments ({pending}) will be translated now.")
                if failed:
                    print(f"  → Failed segments ({failed}) will be retried (up to {max_retries} attempts each).")
                print(f"\nContinuing the chapter run from saved progress...")
                resume_start = time.monotonic()
                with _orchestrator_progress_logging():
                    try:
                        result = orchestrator.resume(
                            text,
                            manifest_path,
                            translate_draft_fn=translate_fn,
                            assets_mode=assets_mode,
                            resume_config=resume_config,
                            smoke_test=smoke_test,
                            model_profile=profile_obj,
                            book_memory=book_memory,
                        )
                    except Exception as e:
                        print(f"  Error: Resume failed: {e}")
                        print("  Starting a fresh run instead.")
                        result = None
                if result is not None:
                    _report_chapter_result(result, output_path, elapsed_seconds=time.monotonic() - resume_start)
                    return
                else:
                    print("  Could not resume. Starting a fresh run.")
            else:
                print("  The saved run cannot be resumed because it is already complete or no longer resumable.")
                print("  Starting a fresh run.")
        else:
            print(f"No manifest found at {manifest_path}.")
            print(f"  (The manifest is created automatically when a chapter run starts.)")
            print(f"  Starting a fresh run.")

    # ── Fresh run path ───────────────────────────────────────────────────
    git_ref = resolve_git_ref()

    plan = orchestrator.plan(text)
    print(f"Chapter: '{plan.chapter_title}' ({plan.segment_count} segments)")
    if book_memory is not None:
        print(f"BookMemory: {book_memory.book_title!r} ({len(book_memory.entities)} entities)")
    print(f"\nTranslating using {mode}...")

    run_start = time.monotonic()
    with _orchestrator_progress_logging():
        try:
            result = orchestrator.run_with_manifest(
                text,
                translate_draft_fn=translate_fn,
                assets_mode=assets_mode,
                resume_config=resume_config,
                manifest_path=manifest_path,
                smoke_test=smoke_test,
                model_profile=profile_obj,
                book_memory=book_memory,
            )
        except Exception as e:
            print(f"  Error: Chapter translation pipeline failed: {e}")
            sys.exit(1)

    # Stage 4: tag the run manifest with git ref for traceability.
    if git_ref and result.manifest and result.manifest.manifest_path:
        result.manifest.git_ref = git_ref
        result.manifest.save()

    _report_chapter_result(result, output_path, elapsed_seconds=time.monotonic() - run_start)


def _display_plan(plan) -> None:
    """Print a human-readable chapter plan summary to stdout.

    CLI-only helper. Not reused for HTTP or programmatic callers.
    """
    strategy = plan.strategy_plan
    print(f"Chapter: '{plan.chapter_title}' ({plan.segment_count} segments)")
    if strategy:
        complexity = strategy.get("complexity", {})
        overall = strategy.get("overall_strategy", {})
        if complexity:
            level = complexity.get("level", "—")
            score = complexity.get("score")
            mode = overall.get("processing_mode", "—") if overall else "—"
            line = f"  Complexity:     {level}"
            if score is not None:
                try:
                    line += f" ({float(score):.2f})"
                except (TypeError, ValueError):
                    line += f" ({score})"
            line += f" · Mode: {mode}"
            print(line)
        if overall:
            seg = overall.get("segmentation_granularity", "—")
            budget = overall.get("budget_profile", "—")
            cons = overall.get("consistency_intensity", "—")
            print(f"  Segmentation:   {seg} · {plan.segment_count} segments · Budget: {budget}")
            print(f"  Consistency:    {cons}")
        rationale = strategy.get("rationale")
        if rationale:
            print(f"  Rationale:      {rationale}")


def _report_chapter_result(result: ChapterResult, output_path: Path, elapsed_seconds: Optional[float] = None) -> None:
    """Print a status summary and write output for a chapter run result.

    Batch 3 addition: reports consistency audit findings and correction
    summary when available as a one-line status summary with category
    breakdown when issues exist.
    """
    status_label = result.chapter_status.value

    # Smoke-test mode: show prominent banner and override quality report to
    # prevent the output from being mistaken for a normal quality pass.
    if result.smoke_test:
        print("\n■■■  SMOKE TEST MODE  ■■■")
        print("  No real model backend. Output is mock — not a real translation.")
        print(f"\nChapter '{result.chapter_title}' result:")
        print(f"  Status:      {status_label} (smoke test)")
        print(f"  Completed:   {result.success_count}/{result.segment_count} segments")
        print(f"  Quality:     SKIPPED (smoke test)")
    else:
        print(f"\nChapter '{result.chapter_title}' result:")
        print(f"  Status:      {status_label}")
        print(f"  Completed:   {result.success_count}/{result.segment_count} segments")

        # Quality gate — surfaced before consistency so operators cannot miss a
        # quality fail when the run is otherwise marked "completed".
        quality = getattr(result, "quality_report", None)
        if quality is not None:
            if quality.passed and quality.error_count == 0 and quality.warning_count == 0:
                print(f"  Quality:     passed")
            elif quality.passed:
                print(f"  Quality:     passed ({quality.warning_count} warning(s))")
            else:
                print(
                    f"  Quality:     FAILED — {quality.error_count} error(s) "
                    f"[{', '.join(quality.codes())}]"
                )
                for issue in quality.issues:
                    if issue.severity == "error":
                        seg = f" (segment {issue.segment_id})" if issue.segment_id else ""
                        print(f"    - {issue.code}{seg}: {issue.message}")
    if result.failed_segment_ids:
        if result.success_count == 0:
            # All segments failed — compact summary avoids noise
            print(f"  Failed:      all {len(result.failed_segment_ids)} segments")
        else:
            # Mixed result: individual failures are actionable
            print(f"  Failed:      {len(result.failed_segment_ids)} segments")
            for fid in result.failed_segment_ids:
                rec = result.manifest.segments.get(fid) if result.manifest else None
                err = f" ({rec.error_message})" if rec and rec.error_message else ""
                print(f"    - Segment {fid}{err}")


    # Write output — prefer corrected version when available
    output_text = result.final_translation
    if result.is_complete or result.is_partial:
        output_path.parent.mkdir(parents=True, exist_ok=True)
        if output_text:
            output_path.write_text(output_text, encoding='utf-8')
            labels = []
            if result.corrected_translation is not None:
                labels.append("post-consistency")
            if result.is_partial:
                labels.append(f"partial — {result.success_count}/{result.segment_count} segments")
            suffix = f" ({', '.join(labels)})" if labels else ""
            if result.smoke_test:
                print(f"  Written to:  {output_path} (smoke test — not a real translation)")
            else:
                print(f"  Written to:  {output_path}{suffix}")
        else:
            print(f"  No output written: translation is empty.")
    else:
        if result.failed_segment_ids and result.success_count == 0:
            print(f"  No output written: all segments failed.")
        else:
            print(f"  No output written: chapter status is '{status_label}'.")

    # Manifest + resume guidance (consolidated)
    manifest_path = result.manifest.manifest_path if result.manifest else None
    if result.is_partial and manifest_path:
        completed = result.success_count
        pending_failed = result.segment_count - completed
        print(f"  Manifest:    {manifest_path}")
        print(f"  Next step:   run with --resume to continue")
        print(f"               (reuses {completed} completed segments; "
              f"processes {pending_failed} remaining segments, subject to retry limits)")
    elif result.resumable and manifest_path:
        # All segments failed — still resumable
        print(f"  Manifest:    {manifest_path}")
        print(f"  Next step:   run with --resume to retry all segments")
    elif manifest_path:
        # Completed or terminal — manifest is a run record
        smoke_tag = " (smoke test)" if result.smoke_test else ""
        print(f"  Manifest:    {manifest_path}{smoke_tag}")

    # Batch 3: consistency report — readable status summary
    if result.smoke_test:
        print(f"  Consistency:     SKIPPED (smoke test)")
    elif result.consistency_audit:
        audit = result.consistency_audit
        correction = result.correction_summary
        total = audit['total_issues']
        auto_fixed = audit['auto_fixed']
        if total == 0:
            print(f"  Consistency:     no issues found")
        elif auto_fixed == total:
            plural = "s" if total != 1 else ""
            print(f"  Consistency:     all resolved ({total} issue{plural} auto-fixed)")
        elif auto_fixed > 0:
            print(f"  Consistency:     {total} issues ({auto_fixed} auto-fixed)")
        else:
            print(f"  Consistency:     {total} issues found")
        if total > 0:
            for cat, count in sorted(audit['by_category'].items()):
                print(f"    {cat}: {count}")
        if correction and correction['total_corrections'] > 0:
            print(f"  Corrections:")
            for cat, count in sorted(correction['by_category'].items()):
                print(f"    {cat}: {count}")
        if result.corrected_translation is not None:
            print(f"  Corrected:       {len(result.corrected_translation)} chars (post-consistency)")

    # Strategy overview: display planned strategy from existing fields only.
    strategy = result.strategy_plan_summary
    if strategy:
        complexity = strategy.get("complexity", {})
        overall = strategy.get("overall_strategy", {})
        if complexity or overall:
            print(f"  Strategy:")
        if complexity:
            level = complexity.get("level", "—")
            score = complexity.get("score")
            mode = overall.get("processing_mode", "—") if overall else "—"
            line = f"    Complexity:   {level}"
            if score is not None:
                line += f" ({score:.2f})"
            line += f" · Mode: {mode}"
            print(line)
        if overall:
            seg = overall.get("segmentation_granularity", "—")
            budget = overall.get("budget_profile", "—")
            cons = overall.get("consistency_intensity", "—")
            print(f"    Segmentation: {seg} · {result.segment_count} segments · Budget: {budget}")
            print(f"    Consistency:  {cons}")

    if elapsed_seconds is not None:
        print(f"Elapsed: {elapsed_seconds:.1f}s")

    if result.smoke_test:
        print("Done (smoke test).")
    else:
        print("Done.")


def run_chapter_stream(
    source_path: Optional[Path] = None,
    service_url: Optional[str] = None,
    allow_mock_fallback: bool = False,
    assets_mode: AssetsMode = DEFAULT_ASSETS_MODE,
    model_profile: Optional[str] = None,
    smoke_test: bool = False,
    book_memory_path: Optional[Path] = None,
) -> None:
    """Stream chapter translation: read source, translate, output final text to stdout.

    If source_path is None, read from stdin.
    """
    _validate_assets_mode(assets_mode)

    # ── Stage 4: Pre-run validation ──────────────────────────────────────
    if source_path is not None:
        vresult = validate_chapter_run(
            source_path=source_path,
            book_memory_path=book_memory_path,
            is_dry_run=True,  # stream doesn't support --dry-run, skip advisory
        )
        for line in vresult.format_lines():
            sys.stderr.write(line + "\n")
        if not vresult.passed:
            sys.exit(1)

    # Read source text
    if source_path is not None:
        text = read_source_file(source_path)
    else:
        # Read from stdin
        text = sys.stdin.read()

    if not text.strip():
        sys.stderr.write("ERROR: source text cannot be empty.\n")
        sys.exit(1)

    # Resolve translation function (same logic as chapter pipeline)
    translate_fn, mode = _resolve_translate_fn(service_url, allow_mock_fallback, assets_mode, model_profile=model_profile)
    if translate_fn is None:
        sys.stderr.write("ERROR: Service unavailable and fallback not allowed.\n")
        sys.exit(1)

    # Resolve the profile object for review/polish orchestration.
    profile_obj = None
    if model_profile:
        from app.translate.model_profiles import get_profile
        profile_obj = get_profile(model_profile)

    set_smoke_mode(smoke_test)

    # Load BookMemory (if provided)
    book_memory = load_book_memory(book_memory_path)

    # Run chapter translation
    try:
        orchestrator = ChapterOrchestrator()
        result = orchestrator.run_with_manifest(
            text,
            translate_draft_fn=translate_fn,
            assets_mode=assets_mode,
            manifest_path=None,  # No persistent manifest for stream mode
            smoke_test=smoke_test,
            model_profile=profile_obj,
            book_memory=book_memory,
        )
    except Exception as e:
        sys.stderr.write(f"Chapter translation failed: {e}\n")
        sys.exit(1)

    # Output final translation text to stdout
    output_text = result.final_translation
    if output_text:
        sys.stdout.write(output_text + "\n")
    else:
        sys.stderr.write("ERROR: No translation output produced.\n")
        sys.exit(1)


@dataclass
class BatchChapterResult:
    """Result of a single chapter run within a batch."""
    source: Path
    output: Path
    status: str  # "COMPLETED" or "FAILED"
    error: Optional[str] = None


def run_chapter_batch(
    source_paths: List[Path],
    service_url: Optional[str] = None,
    allow_mock_fallback: bool = False,
    assets_mode: AssetsMode = DEFAULT_ASSETS_MODE,
    model_profile: Optional[str] = None,
    resume: bool = False,
    no_clobber: bool = False,
    smoke_test: bool = False,
    book_memory_path: Optional[Path] = None,
) -> None:
    """Run chapter translation for multiple source files.

    Processes each source file sequentially. One failed chapter does
    not stop subsequent chapters. Produces a per-chapter summary at
    the end.
    """
    _validate_assets_mode(assets_mode)
    results: List[BatchChapterResult] = []

    print(f"Batch translation: {len(source_paths)} source(s)")
    print()

    for i, source in enumerate(source_paths, 1):
        output = _derive_output_path(source)
        print(f"[{i}/{len(source_paths)}] {source.name}")
        print(f"  Source:  {source}")
        print(f"  Output:  {output}")
        print()

        try:
            run_chapter_pipeline(
                source_path=source,
                output_path=output,
                service_url=service_url,
                allow_mock_fallback=allow_mock_fallback,
                assets_mode=assets_mode,
                model_profile=model_profile,
                resume=resume,
                no_clobber=no_clobber,
                smoke_test=smoke_test,
                book_memory_path=book_memory_path,
            )
            # Check actual output: run_chapter_pipeline can return without
            # SystemExit even when translation failed (e.g., model backend
            # unavailable). Treat missing output as a chapter failure.
            if output.exists():
                status = "COMPLETED"
                error = None
            else:
                status = "FAILED"
                error = "no output produced"
            results.append(BatchChapterResult(
                source=source, output=output, status=status, error=error,
            ))
        except SystemExit as e:
            if e.code == 0:
                raise  # user-initiated cancel propagates
            error_msg = str(e) if str(e) else "chapter failed"
            results.append(BatchChapterResult(
                source=source, output=output, status="FAILED", error=error_msg,
            ))
        except Exception as e:
            error_msg = str(e) if str(e) else type(e).__name__
            results.append(BatchChapterResult(
                source=source, output=output, status="FAILED", error=error_msg,
            ))
        print()

    # ── Batch summary ─────────────────────────────────────────────────
    completed = sum(1 for r in results if r.status == "COMPLETED")
    failed = sum(1 for r in results if r.status == "FAILED")

    print("--- Batch Summary ---")
    for r in results:
        line = f"  {r.source.name:40s} {r.status:<10s}"
        if r.error:
            line += f"  {r.error}"
        print(line)
    print(f"  ({len(results)} source(s) · {completed} completed · {failed} failed)")
    print()
    if failed:
        print("  (One or more chapters failed. Check individual run output above.)")


def main():
    parser = argparse.ArgumentParser(description="Novel translation workbench MVP")
    subparsers = parser.add_subparsers(dest='command', required=True)

    run_parser = subparsers.add_parser('run', help='Run translation pipeline')
    # Optional arguments for input/output paths
    run_parser.add_argument('--source', type=Path, default=None,
                            help='Path to source text file (default: project-root/data/source/one_chapter_quality_source.txt)')
    run_parser.add_argument('--output', type=Path, default=None,
                            help='Path to output markdown file (default: derived from --source, e.g. data/exports/<source-stem>_en.md)')
    run_parser.add_argument('--service-url', type=str, default=None,
                            help='URL of translation service (e.g., http://localhost:8000). If not provided, use local mock.')
    run_parser.add_argument('--allow-mock-fallback', action='store_true',
                            help='If service fails, allow falling back to local mock translation.')
    run_parser.add_argument('--assets-mode', dest='assets_mode',
                            choices=list(ASSETS_MODES), default=DEFAULT_ASSETS_MODE,
                            help='Project-asset injection mode. "full" (default) injects '
                                 'the project memory block into translation prompts; "none" '
                                 'suppresses it entirely.')
    run_parser.add_argument('--model-profile', type=str, default=None,
                            help='Select a model profile (e.g. local-qwen, deepseek-v4-flash, '
                                 'deepseek-v4-pro). When set, overrides MODEL_BACKEND_URL.')

    chapter_parser = subparsers.add_parser('chapter', help='Translate a full chapter (auto-segment -> auto-translate -> aggregate -> consistency)')
    chapter_sub = chapter_parser.add_subparsers(dest='chapter_command', required=True)
    chapter_run_parser = chapter_sub.add_parser('run', help='Run chapter-level translation pipeline')
    chapter_run_parser.add_argument('--source', type=Path, default=None,
                                    help='Path to full chapter source text file (default: project-root/data/source/one_chapter_quality_source.txt)')
    chapter_run_parser.add_argument('--output', type=Path, default=None,
                                    help='Path to final chapter-level output file (default: derived from --source, e.g. data/exports/<source-stem>_en.md)')
    chapter_run_parser.add_argument('--service-url', type=str, default=None,
                                    help='URL of translation service (e.g., http://localhost:8000). If not provided, use local mock.')
    chapter_run_parser.add_argument('--allow-mock-fallback', action='store_true',
                                    help='If service fails, allow falling back to local mock translation.')
    chapter_run_parser.add_argument('--assets-mode', dest='assets_mode',
                                    choices=list(ASSETS_MODES), default=DEFAULT_ASSETS_MODE,
                                    help='Project-asset injection mode. "full" (default) injects '
                                         'the project memory block into translation prompts; "none" '
                                         'suppresses it entirely.')
    chapter_run_parser.add_argument('--model-profile', type=str, default=None,
                                    help='Select a model profile (e.g. local-qwen, deepseek-v4-flash, '
                                         'deepseek-v4-pro). When set, overrides --service-url and MODEL_BACKEND_URL.')
    # --resume and --dry-run are mutually exclusive
    resume_group = chapter_run_parser.add_mutually_exclusive_group()
    resume_group.add_argument('--resume', action='store_true',
                              help='Resume an incomplete chapter run from its saved manifest. '
                                   'Completed segments are reused; pending and failed segments '
                                   'are processed again subject to retry limits. The manifest '
                                   'file lives at <output>.manifest.json. Use this to continue '
                                   'a partial or interrupted chapter run.')
    resume_group.add_argument('--dry-run', action='store_true',
                              help='Preview the chapter plan and exit without translating. '
                                   'Shows segment count, complexity, and strategy decisions. '
                                   'Cannot be combined with --resume.')
    chapter_run_parser.add_argument('--max-retries', type=int, default=2,
                                    help='Maximum number of retry attempts per segment before marking it failed (default: 2).')
    chapter_run_parser.add_argument('--retry-delay-seconds', type=float, default=1.0,
                                    help='Base delay between retry attempts in seconds (default: 1.0).')
    chapter_run_parser.add_argument('--no-auto-retry-on-resume', action='store_false', dest='auto_retry_on_resume',
                                    help='Disable automatic retry of failed segments on resume (default: auto-retry enabled).')
    chapter_run_parser.add_argument('--no-clobber', action='store_true',
                                    help='Do not overwrite an existing output file. Exit with an error if the output path already exists.')
    chapter_run_parser.add_argument('--confirm', action='store_true',
                                    help='Show chapter plan and wait for confirmation before executing. '
                                         'Useful after --dry-run to preview then decide, or standalone '
                                         'to see the plan before starting a fresh run.')
    chapter_run_parser.add_argument('--book-memory', type=Path, default=None,
                                    help='Path to a BookMemory JSON file. When provided, context packs '
                                         'are built from book memory for each segment and injected into '
                                         'translation prompts (R3/R4).')
    chapter_run_parser.add_argument('--smoke-test', action='store_true',
                                    help='Run in smoke-test mode (no real model backend required). '
                                         'Translates mechanically with mock output. Quality gates '
                                         'and consistency passes are skipped. Output is clearly '
                                         'labeled as smoke test — not a real translation.')

    chapter_stream_parser = chapter_sub.add_parser('stream', help='Stream chapter translation: read source, translate, output final translation to stdout')
    chapter_stream_parser.add_argument('--source', type=Path, default=None,
                                       help='Path to full chapter source text file (if omitted, read from stdin)')
    chapter_stream_parser.add_argument('--service-url', type=str, default=None,
                                       help='URL of translation service (e.g., http://localhost:8000). If not provided, use local mock.')
    chapter_stream_parser.add_argument('--allow-mock-fallback', action='store_true',
                                       help='If service fails, allow falling back to local mock translation.')
    chapter_stream_parser.add_argument('--assets-mode', dest='assets_mode',
                                       choices=list(ASSETS_MODES), default=DEFAULT_ASSETS_MODE,
                                       help='Project-asset injection mode. "full" (default) injects '
                                            'the project memory block into translation prompts; "none" '
                                            'suppresses it entirely.')
    chapter_stream_parser.add_argument('--model-profile', type=str, default=None,
                                       help='Select a model profile (e.g. local-qwen, deepseek-v4-flash, '
                                            'deepseek-v4-pro).')
    chapter_stream_parser.add_argument('--book-memory', type=Path, default=None,
                                        help='Path to a BookMemory JSON file for context pack injection (R3/R4).')
    chapter_stream_parser.add_argument('--smoke-test', action='store_true',
                                       help='Run in smoke-test mode (no real model backend required). '
                                            'Output is mock — not a real translation.')

    chapter_batch_parser = chapter_sub.add_parser('batch', help='Run batch chapter translation for multiple source files')
    chapter_batch_parser.add_argument('--source', type=Path, required=True, action='append',
                                      help='Path to chapter source text file (repeatable, required). Each source '
                                           'gets its own default output path derived from its filename.')
    chapter_batch_parser.add_argument('--service-url', type=str, default=None,
                                      help='URL of translation service (e.g., http://localhost:8000). If not provided, use local mock.')
    chapter_batch_parser.add_argument('--allow-mock-fallback', action='store_true',
                                      help='If service fails, allow falling back to local mock translation.')
    chapter_batch_parser.add_argument('--assets-mode', dest='assets_mode',
                                      choices=list(ASSETS_MODES), default=DEFAULT_ASSETS_MODE,
                                      help='Project-asset injection mode. "full" (default) injects '
                                           'the project memory block into translation prompts; "none" '
                                           'suppresses it entirely.')
    chapter_batch_parser.add_argument('--model-profile', type=str, default=None,
                                      help='Select a model profile (e.g. local-qwen, deepseek-v4-flash, '
                                           'deepseek-v4-pro).')
    chapter_batch_parser.add_argument('--resume', action='store_true',
                                      help='Attempt to resume each chapter from its saved manifest.')
    chapter_batch_parser.add_argument('--book-memory', type=Path, default=None,
                                       help='Path to a BookMemory JSON file for context pack injection (R3/R4).')
    chapter_batch_parser.add_argument('--smoke-test', action='store_true',
                                      help='Run in smoke-test mode (no real model backend required). '
                                           'Translates mechanically with mock output. Quality gates '
                                           'and consistency passes are skipped.')
    chapter_batch_parser.add_argument('--no-clobber', action='store_true',
                                      help='Skip chapters whose output file already exists.')

    # ── chapter inspect command ────────────────────────────────────────
    chapter_inspect_parser = chapter_sub.add_parser(
        'inspect',
        help='Phase C Stage 5 validation helper: summarize artifact paths, '
             'manifest quality, and next-step guidance for a completed chapter run.',
    )
    chapter_inspect_parser.add_argument(
        '--source', type=Path, required=True,
        help='Path to the chapter source text file. Artifact paths are derived '
             'from the source filename stem.',
    )
    chapter_inspect_parser.add_argument(
        '--output', type=Path, default=None,
        help='Path to the output file (default: derived from --source). '
             'Use this when a non-standard output path was used for the run.',
    )

    # ── workspace-check command ────────────────────────────────────────
    check_parser = subparsers.add_parser(
        'check',
        help='Report workspace hygiene: classify dirty/untracked/generated files by category.',
    )
    check_parser.add_argument(
        '--project-root', type=Path, default=None,
        help='Project root directory (default: auto-detect from CWD).',
    )

    args = parser.parse_args()

    # Resolve default source paths relative to project root.
    if args.command == 'run':
        if args.source is None:
            args.source = find_project_root() / 'data/source/one_chapter_quality_source.txt'
        else:
            args.source = _resolve_source(args.source)
    elif args.command == 'chapter':
        if args.chapter_command == 'run':
            if args.source is None:
                args.source = find_project_root() / 'data/source/one_chapter_quality_source.txt'
            else:
                args.source = _resolve_source(args.source)
        elif args.chapter_command == 'inspect' and args.source is not None:
            args.source = _resolve_source(args.source)

    if args.command == 'run':
        if args.output is None:
            args.output = _derive_output_path(args.source)
        # Ensure output directory exists
        args.output.parent.mkdir(parents=True, exist_ok=True)
        run_pipeline(
            args.source,
            args.output,
            args.service_url,
            args.allow_mock_fallback,
            assets_mode=args.assets_mode,
            model_profile=args.model_profile,
        )
    elif args.command == 'chapter':
        if args.chapter_command == 'run':
            if args.output is None:
                args.output = _derive_output_path(args.source)
            run_chapter_pipeline(
                args.source,
                args.output,
                args.service_url,
                args.allow_mock_fallback,
                assets_mode=args.assets_mode,
                model_profile=args.model_profile,
                resume=args.resume,
                dry_run=args.dry_run,
                max_retries=args.max_retries,
                retry_delay_seconds=args.retry_delay_seconds,
                auto_retry_on_resume=args.auto_retry_on_resume,
                no_clobber=args.no_clobber,
                confirm=args.confirm,
                smoke_test=args.smoke_test,
                book_memory_path=args.book_memory,
            )
        elif args.chapter_command == 'stream':
            run_chapter_stream(
                source_path=args.source,
                service_url=args.service_url,
                allow_mock_fallback=args.allow_mock_fallback,
                assets_mode=args.assets_mode,
                model_profile=args.model_profile,
                smoke_test=args.smoke_test,
                book_memory_path=args.book_memory,
            )
        elif args.chapter_command == 'batch':
            run_chapter_batch(
                source_paths=args.source,
                service_url=args.service_url,
                allow_mock_fallback=args.allow_mock_fallback,
                assets_mode=args.assets_mode,
                model_profile=args.model_profile,
                resume=args.resume,
                no_clobber=args.no_clobber,
                smoke_test=args.smoke_test,
                book_memory_path=args.book_memory,
            )
        elif args.chapter_command == 'inspect':
            from app.chapter.inspector import (
                find_artifacts,
                format_inspection_guide,
                load_manifest,
            )

            source_stem = args.source.stem
            artifacts = find_artifacts(source_stem)
            summary = load_manifest(artifacts.manifest)
            output = format_inspection_guide(artifacts, summary)
            print(output)
    elif args.command == 'check':
        from app.hygiene.reporter import scan_workspace
        report = scan_workspace(project_root=args.project_root)
        report.print_report()
    else:
        parser.print_help()


if __name__ == '__main__':
    main()