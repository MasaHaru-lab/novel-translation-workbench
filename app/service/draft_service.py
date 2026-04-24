"""
FastAPI service for draft translation.

Exposes a single endpoint POST /translate/draft that calls a local model backend.
"""
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field
from typing import List, Optional, Dict, Any
import uvicorn

from app.translate.schema import TranslationInput, TranslationOutput, GlossaryTerm
from app.translate.backend_adapter import translate_draft_with_backend
from app.config import config
from app.chapter.orchestrator import ChapterOrchestrator
from app.chapter.models import ChapterResult


app = FastAPI(
    title="Novel Translation Workbench Draft Service",
    description="Minimal HTTP service for draft translation using local model backend",
    version="0.1.0"
)


# We need Pydantic models that mirror the dataclasses for FastAPI request/response
# because FastAPI doesn't support dataclasses directly for request bodies.
class GlossaryTermModel(BaseModel):
    zh: str
    en: str

    class Config:
        from_attributes = True


class TranslationInputModel(BaseModel):
    segment_id: str
    source_text: str
    prev_context: Optional[str] = None
    next_context: Optional[str] = None
    glossary_terms: List[GlossaryTermModel] = []

    class Config:
        from_attributes = True


class TranslationOutputModel(BaseModel):
    segment_id: str
    draft_translation: str
    polished_translation: str
    notes: List[str] = []

    class Config:
        from_attributes = True


class ChapterRequestModel(BaseModel):
    """Request model for chapter translation endpoint."""
    source_text: str
    # Additional parameters could be added later (e.g., glossary, custom strategy)


class ChapterResponseModel(BaseModel):
    """Response model for chapter translation endpoint."""
    chapter_title: str
    aggregated_translation: str
    corrected_translation: Optional[str] = None
    chapter_status: str
    consistency_audit: Optional[Dict[str, Any]] = None
    correction_summary: Optional[Dict[str, Any]] = None
    strategy_plan_summary: Optional[Dict[str, Any]] = None
    enactment: Optional[Dict[str, Any]] = None
    segment_count: int
    success_count: int
    failed_segment_ids: List[str] = Field(default_factory=list)
    resumable: bool
    readable_summary: str = ""

    class Config:
        from_attributes = True


@app.post("/translate/draft", response_model=TranslationOutputModel)
async def post_translate_draft(input: TranslationInputModel) -> TranslationOutputModel:
    """Return a draft translation using the configured model backend."""
    # Convert Pydantic model to dataclass
    glossary_terms = [
        GlossaryTerm(zh=term.zh, en=term.en) for term in input.glossary_terms
    ]
    translation_input = TranslationInput(
        segment_id=input.segment_id,
        source_text=input.source_text,
        prev_context=input.prev_context,
        next_context=input.next_context,
        glossary_terms=glossary_terms
    )

    # Check backend configuration
    if not config.MODEL_BACKEND_URL.strip():
        raise HTTPException(
            status_code=503,
            detail="Model backend not configured. Set MODEL_BACKEND_URL environment variable."
        )

    # Call real backend adapter
    try:
        output = translate_draft_with_backend(translation_input)
    except RuntimeError as e:
        raise HTTPException(
            status_code=503,
            detail=f"Model backend error: {str(e)}"
        )

    # Convert to Pydantic model for response
    return TranslationOutputModel(
        segment_id=output.segment_id,
        draft_translation=output.draft_translation,
        polished_translation=output.polished_translation,
        notes=output.notes
    )


def _format_chapter_summary(result: ChapterResult) -> str:
    """Build a human-readable summary string from a ChapterResult.

    Complements the structured ChapterResponseModel fields with a concise,
    operator-facing summary similar to what the CLI prints after a chapter run.
    """
    lines = []

    status = result.chapter_status.value
    lines.append(f"Status: {status} — {result.success_count}/{result.segment_count} segments completed")

    # Failed segments
    if result.failed_segment_ids:
        if result.success_count == 0:
            lines.append(f"Failed: all {len(result.failed_segment_ids)} segments")
        else:
            lines.append(f"Failed: {len(result.failed_segment_ids)} segments")
            for fid in result.failed_segment_ids:
                rec = result.manifest.segments.get(fid) if result.manifest else None
                err = f" ({rec.error_message})" if rec and rec.error_message else ""
                lines.append(f"  - Segment {fid}{err}")

    # Resumable / next-step guidance
    remaining = result.segment_count - result.success_count
    if result.is_partial and remaining > 0:
        lines.append(f"Remaining: {remaining} segment(s) to complete")
    if result.resumable:
        if remaining > 0:
            lines.append(f"Next step: run with --resume to continue "
                         f"(reuses {result.success_count} completed, "
                         f"processes {remaining} remaining)")
        else:
            lines.append("Next step: retry failed segments with --resume")

    # Aggregated/corrected char counts
    if result.aggregated_translation:
        agg_len = len(result.aggregated_translation)
        suffix = " (pre-consistency)" if result.corrected_translation is not None else ""
        lines.append(f"Aggregated: {agg_len} chars{suffix}")
    if result.corrected_translation is not None:
        lines.append(f"Corrected:  {len(result.corrected_translation)} chars (post-consistency)")

    # Strategy overview
    strategy = result.strategy_plan_summary
    if strategy:
        complexity = strategy.get("complexity", {})
        overall = strategy.get("overall_strategy", {})
        parts = []
        if complexity:
            level = complexity.get("level", "—")
            score = complexity.get("score")
            if score is not None:
                parts.append(f"complexity={level} ({score:.2f})")
            else:
                parts.append(f"complexity={level}")
        if overall:
            mode = overall.get("processing_mode", "—")
            budget = overall.get("budget_profile", "—")
            intensity = overall.get("consistency_intensity", "—")
            parts.append(f"mode={mode}")
            parts.append(f"budget={budget}")
            parts.append(f"consistency={intensity}")
        if parts:
            lines.append("Strategy: " + ", ".join(parts))

    # Consistency audit
    audit = result.consistency_audit
    if audit is not None:
        total = audit.get("total_issues", 0)
        auto_fixed = audit.get("auto_fixed", 0)
        if total == 0:
            lines.append("Consistency: no issues found")
        elif auto_fixed == total:
            plural = "s" if total != 1 else ""
            lines.append(f"Consistency: all resolved ({total} issue{plural} auto-fixed)")
        elif auto_fixed > 0:
            lines.append(f"Consistency: {total} issues ({auto_fixed} auto-fixed)")
        else:
            lines.append(f"Consistency: {total} issues found")
        if total > 0:
            for cat, count in sorted(audit.get("by_category", {}).items()):
                lines.append(f"  {cat}: {count}")

    # Correction summary
    correction = result.correction_summary
    if correction and correction.get("total_corrections", 0) > 0:
        lines.append("Corrections:")
        for cat, count in sorted(correction.get("by_category", {}).items()):
            lines.append(f"  {cat}: {count}")

    # Manifest path
    manifest_path = result.manifest.manifest_path if result.manifest else None
    if manifest_path:
        lines.append(f"Manifest: {manifest_path}")

    return "\n".join(lines)


@app.post("/translate/chapter", response_model=ChapterResponseModel)
async def post_translate_chapter(request: ChapterRequestModel) -> ChapterResponseModel:
    """Translate a full chapter using the chapter-level orchestrator."""
    # Validate input
    if not request.source_text.strip():
        raise HTTPException(
            status_code=400,
            detail="source_text cannot be empty"
        )

    try:
        orchestrator = ChapterOrchestrator()
        # Use default parameters for glossary, translate_draft_fn, assets_mode, etc.
        result = orchestrator.run_with_manifest(source_text=request.source_text)
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Internal server error during chapter translation: {str(e)}"
        )

    # Map ChapterResult to ChapterResponseModel
    return ChapterResponseModel(
        chapter_title=result.chapter_title,
        aggregated_translation=result.aggregated_translation,
        corrected_translation=result.corrected_translation,
        chapter_status=result.chapter_status.value,  # enum to string
        consistency_audit=result.consistency_audit,
        correction_summary=result.correction_summary,
        strategy_plan_summary=result.strategy_plan_summary,
        enactment=result.enactment,
        segment_count=result.segment_count,
        success_count=result.success_count,
        failed_segment_ids=result.failed_segment_ids,
        resumable=result.resumable,
        readable_summary=_format_chapter_summary(result),
    )


@app.get("/health")
async def health():
    """Health check endpoint."""
    return {"status": "healthy"}


if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8000)