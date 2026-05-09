"""
FastAPI service for draft translation.

Exposes a single endpoint POST /translate/draft that calls a local model backend.
"""
from fastapi import FastAPI, File, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field
from typing import List, Optional, Dict, Any
from threading import Lock
import os
import uvicorn

from app.translate.schema import TranslationInput, TranslationOutput, GlossaryTerm
from app.translate.backend_adapter import (
    translate_draft_with_backend,
    translate_draft_with_profile,
)
from app.translate.translator import set_smoke_mode
from app.config import config
from app.chapter.orchestrator import ChapterOrchestrator
from app.chapter.models import ChapterResult
from app.chapter.manifest import ResumeConfig
from app.library.intake import BookImportError, import_novel
from app.library.models import Book, BookJob
from app.library.runner import BookRunnerError, run_next_chapter
from app.library.store import (
    book_dir,
    book_exists,
    chapter_path,
    list_chapter_files,
    load_book,
    load_job,
)


app = FastAPI(
    title="Novel Translation Workbench Draft Service",
    description="Minimal HTTP service for draft translation using local model backend",
    version="0.1.0"
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "https://novel-translation-workbench-ui.vercel.app",
        "http://localhost:3000",
        "http://127.0.0.1:3000",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

_smoke_run_lock = Lock()
CHAPTER_API_MODE_ENV = "CHAPTER_API_MODE"
PRODUCT_CHAPTER_MODEL_PROFILE = "deepseek-v4-flash"


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
    """Request model for chapter translation endpoint.

    Manifest/resume semantics mirror the chapter CLI:

    - ``manifest_path`` — when set, the run manifest is persisted at this
      path so progress survives interruptions. Required when ``resume`` is
      true. When omitted, the run is in-memory only and cannot be resumed.
    - ``resume`` — when true, load the manifest at ``manifest_path`` and
      continue the prior run instead of starting fresh.
    - ``max_retries`` / ``retry_delay_seconds`` / ``auto_retry_on_resume``
      — optional ``ResumeConfig`` overrides for fresh runs. Ignored on
      resume because the saved manifest carries its own ``ResumeConfig``.
    """
    source_text: str
    manifest_path: Optional[str] = None
    resume: bool = False
    max_retries: Optional[int] = None
    retry_delay_seconds: Optional[float] = None
    auto_retry_on_resume: Optional[bool] = None


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
    manifest_path: Optional[str] = None
    run_id: Optional[str] = None

    class Config:
        from_attributes = True


class ProductChapterRequestModel(BaseModel):
    """Minimal product-facing chapter request."""
    title: Optional[str] = None
    source_text: str
    mode: str = "default"


class ProductSegmentModel(BaseModel):
    segment_id: str
    final_text: str


class ProductChapterResponseModel(BaseModel):
    """Minimal product-facing chapter response."""
    status: str
    title: Optional[str] = None
    final_text: str = ""
    segments: Optional[List[ProductSegmentModel]] = None
    error: Optional[str] = None


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


def _run_product_chapter_smoke(
    source_text: str,
    manifest_path: Optional[str] = None,
) -> ChapterResult:
    """Run the chapter orchestrator without allowing real backend calls.

    ``manifest_path`` is forwarded to ``run_with_manifest`` so callers
    that own a workspace path (the book runner) can persist the per-
    chapter manifest where they want it. Existing callers that omit
    the kwarg get the previous in-memory behavior."""
    with _smoke_run_lock:
        original_backend_url = config.MODEL_BACKEND_URL
        config.MODEL_BACKEND_URL = ""
        set_smoke_mode(True)
        try:
            return ChapterOrchestrator().run_with_manifest(
                source_text=source_text,
                manifest_path=manifest_path,
                smoke_test=True,
            )
        finally:
            set_smoke_mode(False)
            config.MODEL_BACKEND_URL = original_backend_url


def _product_chapter_mode() -> str:
    """Return the product chapter API mode: 'real' or 'smoke'.

    - ``CHAPTER_API_MODE=real`` → real
    - ``CHAPTER_API_MODE=smoke`` → smoke (mock output, no real model calls)
    - unset / any other value → real (default)
    """
    return os.environ.get(CHAPTER_API_MODE_ENV, "real").strip().lower()


def _run_product_chapter_real(
    source_text: str,
    manifest_path: Optional[str] = None,
) -> ChapterResult:
    """Run the product chapter endpoint through the existing DeepSeek profile.

    ``manifest_path`` is forwarded to ``run_with_manifest`` so the
    book runner can persist per-chapter manifests under the book
    workspace. Existing callers that omit the kwarg keep the previous
    in-memory behavior."""
    from app.config_loader import load_env_local
    from app.translate.model_profiles import get_profile

    load_env_local()
    profile = get_profile(PRODUCT_CHAPTER_MODEL_PROFILE)

    def translate_fn(inp: TranslationInput) -> TranslationOutput:
        return translate_draft_with_profile(inp, profile)

    set_smoke_mode(False)
    return ChapterOrchestrator().run_with_manifest(
        source_text=source_text,
        translate_draft_fn=translate_fn,
        manifest_path=manifest_path,
        smoke_test=False,
        model_profile=profile,
    )


@app.post("/api/chapters", response_model=ProductChapterResponseModel)
async def post_api_chapters(request: ProductChapterRequestModel) -> ProductChapterResponseModel:
    """Minimal synchronous endpoint for the deployed product frontend.

    Routes through the existing DeepSeek profile path by default.
    Set ``CHAPTER_API_MODE=smoke`` to use mock output without real model calls.
    """
    if not request.source_text.strip():
        raise HTTPException(status_code=400, detail="source_text cannot be empty")

    title = request.title.strip() if request.title and request.title.strip() else None

    try:
        if _product_chapter_mode() == "smoke":
            result = _run_product_chapter_smoke(request.source_text)
        else:
            result = _run_product_chapter_real(request.source_text)
    except Exception:
        return ProductChapterResponseModel(
            status="error",
            title=title,
            final_text="",
            error="Chapter translation failed before producing output.",
        )

    segments = [
        ProductSegmentModel(
            segment_id=segment.segment_id,
            final_text=segment.polished_translation,
        )
        for segment in result.segment_results
    ]
    return ProductChapterResponseModel(
        status=result.chapter_status.value,
        title=title or result.chapter_title,
        final_text=result.final_translation,
        segments=segments or None,
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


def _build_resume_config(request: ChapterRequestModel) -> Optional[ResumeConfig]:
    """Build a ResumeConfig from request overrides.

    Returns None when no override is supplied so the orchestrator falls back
    to ResumeConfig defaults. Validates non-negative numeric bounds.
    """
    if (request.max_retries is None
            and request.retry_delay_seconds is None
            and request.auto_retry_on_resume is None):
        return None

    if request.max_retries is not None and request.max_retries < 0:
        raise HTTPException(
            status_code=400,
            detail=f"max_retries must be >= 0, got {request.max_retries}",
        )
    if request.retry_delay_seconds is not None and request.retry_delay_seconds < 0:
        raise HTTPException(
            status_code=400,
            detail=f"retry_delay_seconds must be >= 0, got {request.retry_delay_seconds}",
        )

    defaults = ResumeConfig()
    return ResumeConfig(
        max_retries=request.max_retries if request.max_retries is not None else defaults.max_retries,
        retry_delay_seconds=request.retry_delay_seconds if request.retry_delay_seconds is not None else defaults.retry_delay_seconds,
        auto_retry_on_resume=request.auto_retry_on_resume if request.auto_retry_on_resume is not None else defaults.auto_retry_on_resume,
    )


@app.post("/translate/chapter", response_model=ChapterResponseModel)
async def post_translate_chapter(request: ChapterRequestModel) -> ChapterResponseModel:
    """Translate a full chapter using the chapter-level orchestrator.

    Manifest/resume semantics:
      - resume=True requires manifest_path; if the manifest does not exist
        it returns 404; if the manifest is not resumable it returns 409.
      - resume=False starts a fresh run; manifest_path (when set) is where
        the manifest is persisted and the run is later resumable from.
    """
    # Validate input
    if not request.source_text.strip():
        raise HTTPException(
            status_code=400,
            detail="source_text cannot be empty"
        )

    if request.resume and not request.manifest_path:
        raise HTTPException(
            status_code=400,
            detail="manifest_path is required when resume=true",
        )

    resume_config = _build_resume_config(request)
    orchestrator = ChapterOrchestrator()

    try:
        if request.resume:
            existing = orchestrator.load_manifest(request.manifest_path)
            if existing is None:
                raise HTTPException(
                    status_code=404,
                    detail=f"No manifest found at {request.manifest_path}",
                )
            if not existing.is_resumable():
                raise HTTPException(
                    status_code=409,
                    detail=(
                        f"Manifest is not resumable (status={existing.status.value}); "
                        "the saved run is already complete or in a terminal state"
                    ),
                )
            result = orchestrator.run_with_manifest(
                source_text=request.source_text,
                resume_config=resume_config,
                manifest_path=request.manifest_path,
                existing_manifest=existing,
            )
        else:
            result = orchestrator.run_with_manifest(
                source_text=request.source_text,
                resume_config=resume_config,
                manifest_path=request.manifest_path,
            )
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Internal server error during chapter translation: {str(e)}"
        )

    manifest = result.manifest
    return ChapterResponseModel(
        chapter_title=result.chapter_title,
        aggregated_translation=result.aggregated_translation,
        corrected_translation=result.corrected_translation,
        chapter_status=result.chapter_status.value,
        consistency_audit=result.consistency_audit,
        correction_summary=result.correction_summary,
        strategy_plan_summary=result.strategy_plan_summary,
        enactment=result.enactment,
        segment_count=result.segment_count,
        success_count=result.success_count,
        failed_segment_ids=result.failed_segment_ids,
        resumable=result.resumable,
        readable_summary=_format_chapter_summary(result),
        manifest_path=manifest.manifest_path if manifest else None,
        run_id=manifest.run_id if manifest else None,
    )


@app.get("/health")
async def health():
    """Health check endpoint."""
    return {"status": "healthy"}


# ── Library / book-import endpoints ──────────────────────────────────
#
# These wrap app.library and provide the upload + listing surface for
# a frontend that imports a full novel before translating it. They do
# NOT trigger translation — that stays on /translate/chapter and
# /api/chapters until a later batch.


# 25 MB cap on novel uploads. Plain UTF-8 text; ~12.5M Chinese
# characters at the upper bound, generous for any realistic novel.
MAX_BOOK_BYTES = 25 * 1024 * 1024


class BookSummaryModel(BaseModel):
    """Book record exposed to the frontend.

    ``detected_chapter_count`` is what the splitter found at import
    time. The translation contract is sequential — translate the next
    chapter until no next chapter remains — so the frontend should
    treat this as display information, not as a hard upper bound."""

    book_id: str
    title: str
    source_filename: str
    source_hash: str
    detected_chapter_count: int
    has_preamble: bool
    created_at: str


class BookJobModel(BaseModel):
    """Job state exposed to the frontend.

    Mirrors ``detected_chapter_count`` from the Book record; same
    caveat about it being a snapshot rather than an absolute total."""

    book_id: str
    detected_chapter_count: int
    status: str
    completed_chapter_indexes: List[int]
    failed_chapter_indexes: List[int]
    error_message: Optional[str] = None
    created_at: str
    updated_at: str


class ChapterListEntryModel(BaseModel):
    index: int
    heading: str


class BookDetailModel(BaseModel):
    book: BookSummaryModel
    job: BookJobModel
    chapters: List[ChapterListEntryModel]


class ChapterContentModel(BaseModel):
    book_id: str
    index: int
    heading: str
    source_text: str


def _book_to_model(book: Book) -> BookSummaryModel:
    return BookSummaryModel(**book.to_dict())


def _job_to_model(job: BookJob) -> BookJobModel:
    return BookJobModel(**job.to_dict())


def _chapter_index_from_filename(path) -> Optional[int]:
    """Extract the leading 4-digit index from a chapter filename.

    Filenames are written as ``NNNN_<slug>.txt`` by the kernel.
    Returns None when the filename doesn't match.
    """
    stem = path.stem  # "NNNN_slug"
    head = stem.split("_", 1)[0]
    if head.isdigit():
        return int(head)
    return None


def _chapter_listing(book_id: str) -> List[ChapterListEntryModel]:
    """Build the chapter listing by reading just the first non-empty
    line of each chapter file. Cheap on local disk for any realistic
    chapter count."""
    listing: List[ChapterListEntryModel] = []
    for path in list_chapter_files(book_id):
        idx = _chapter_index_from_filename(path)
        if idx is None:
            continue
        heading = ""
        with path.open("r", encoding="utf-8") as f:
            for line in f:
                stripped = line.strip()
                if stripped:
                    heading = stripped
                    break
        listing.append(ChapterListEntryModel(index=idx, heading=heading))
    return listing


def _read_chapter_content(book_id: str, index: int) -> Optional[ChapterContentModel]:
    """Locate the chapter file for ``index`` and return its content.

    Returns None when no file matches the index. Slug is resolved by
    listing the chapters directory rather than recomputed, so a book
    written under one slugger and read under a different one still
    works."""
    for path in list_chapter_files(book_id):
        idx = _chapter_index_from_filename(path)
        if idx == index:
            text = path.read_text(encoding="utf-8")
            heading = ""
            for line in text.splitlines():
                stripped = line.strip()
                if stripped:
                    heading = stripped
                    break
            return ChapterContentModel(
                book_id=book_id,
                index=index,
                heading=heading,
                source_text=text,
            )
    return None


def _build_book_detail(book_id: str) -> Optional[BookDetailModel]:
    """Compose a BookDetailModel by reading Book + Job + chapter listing.

    Returns None when ``book.json`` is missing for ``book_id``."""
    book = load_book(book_id)
    if book is None:
        return None
    job = load_job(book_id)
    if job is None:
        # Book exists but job record is missing — shouldn't happen via the
        # kernel, but surface the partial state rather than hide it.
        raise HTTPException(
            status_code=500,
            detail=f"Book {book_id} has no job record on disk",
        )
    return BookDetailModel(
        book=_book_to_model(book),
        job=_job_to_model(job),
        chapters=_chapter_listing(book_id),
    )


@app.post("/api/books", response_model=BookDetailModel)
async def post_api_books(file: UploadFile = File(...)) -> BookDetailModel:
    """Import a full novel from an uploaded .txt or .md file.

    Returns the freshly created Book + initial pending BookJob plus
    the parsed chapter listing. Re-uploading identical content
    returns the existing book unchanged (idempotent on source hash)."""
    contents = await file.read()
    if len(contents) == 0:
        raise HTTPException(status_code=400, detail="uploaded file is empty")
    if len(contents) > MAX_BOOK_BYTES:
        raise HTTPException(
            status_code=413,
            detail=f"file exceeds {MAX_BOOK_BYTES} byte limit",
        )
    try:
        text = contents.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise HTTPException(
            status_code=400,
            detail=f"file is not valid UTF-8: {exc}",
        )

    original_filename = (file.filename or "").strip() or "upload.txt"
    try:
        book = import_novel(text, original_filename=original_filename)
    except BookImportError as exc:
        raise HTTPException(status_code=400, detail=str(exc))

    detail = _build_book_detail(book.book_id)
    if detail is None:
        # import_novel succeeded but the workspace can't be read back.
        raise HTTPException(
            status_code=500,
            detail="book imported but workspace cannot be read",
        )
    return detail


@app.get("/api/books/{book_id}", response_model=BookDetailModel)
async def get_api_books_detail(book_id: str) -> BookDetailModel:
    """Return Book metadata, current Job state, and chapter listing."""
    if not book_exists(book_id):
        raise HTTPException(status_code=404, detail=f"book {book_id} not found")
    detail = _build_book_detail(book_id)
    if detail is None:
        raise HTTPException(status_code=404, detail=f"book {book_id} not found")
    return detail


@app.get(
    "/api/books/{book_id}/chapters/{index}",
    response_model=ChapterContentModel,
)
async def get_api_books_chapter(book_id: str, index: int) -> ChapterContentModel:
    """Return one chapter's index, original heading, and full source text."""
    if not book_exists(book_id):
        raise HTTPException(status_code=404, detail=f"book {book_id} not found")
    if index < 1:
        raise HTTPException(
            status_code=404,
            detail=f"chapter index must be >= 1, got {index}",
        )
    content = _read_chapter_content(book_id, index)
    if content is None:
        raise HTTPException(
            status_code=404,
            detail=f"chapter {index} not found in book {book_id}",
        )
    return content


# ── Translate-next endpoint ──────────────────────────────────────────
#
# The smallest execution primitive for long-book translation: one
# request translates one next unfinished chapter. The frontend or an
# operator can call it repeatedly to advance the book. Reuses the
# CHAPTER_API_MODE env var ("real" / "smoke") used by /api/chapters
# so a single switch toggles the whole product surface.


class TranslateNextResponseModel(BaseModel):
    """Outcome of a single ``POST /api/books/{book_id}/translate-next``.

    ``ran_index`` is None when no unfinished chapter remained — that
    case is a clean no-op (HTTP 200), not a failure. ``success``
    reflects only whether the chapter actually completed; check
    ``ran_index`` first to distinguish "nothing to do" from "failed".
    """

    book_id: str
    ran_index: Optional[int] = None
    success: bool = False
    chapter_status: Optional[str] = None
    error_message: Optional[str] = None
    output_filename: Optional[str] = None
    book: BookDetailModel


def _translate_chapter_via_product_mode(
    source_text: str,
    manifest_path: str,
) -> ChapterResult:
    """Adapter matching ``ChapterTranslateFn`` for the runner.

    Routes between the existing smoke and real product helpers based
    on ``CHAPTER_API_MODE`` — the same env switch ``/api/chapters``
    uses, so behaviour is consistent across both endpoints.
    """
    if _product_chapter_mode() == "smoke":
        return _run_product_chapter_smoke(source_text, manifest_path=manifest_path)
    return _run_product_chapter_real(source_text, manifest_path=manifest_path)


@app.post(
    "/api/books/{book_id}/translate-next",
    response_model=TranslateNextResponseModel,
)
async def post_api_books_translate_next(
    book_id: str,
) -> TranslateNextResponseModel:
    """Translate the next unfinished chapter of an imported book.

    Synchronous: one HTTP request → one chapter attempt. The runner
    decides which chapter to translate (lowest-indexed on-disk
    chapter that is neither completed nor previously failed) and
    persists job state. A failed chapter attempt returns HTTP 200
    with ``success=false`` and ``error_message`` populated — failures
    are not surfaced as 5xx because the operation itself completed.
    """
    if not book_exists(book_id):
        raise HTTPException(status_code=404, detail=f"book {book_id} not found")

    try:
        result = run_next_chapter(
            book_id,
            _translate_chapter_via_product_mode,
        )
    except BookRunnerError as exc:
        raise HTTPException(status_code=404, detail=str(exc))

    detail = _build_book_detail(book_id)
    if detail is None:
        raise HTTPException(
            status_code=500,
            detail=f"book {book_id} workspace cannot be read after translate-next",
        )

    chapter_status = (
        result.chapter_result.chapter_status.value
        if result.chapter_result is not None
        else None
    )

    output_filename: Optional[str] = None
    if result.success and result.output_path is not None:
        try:
            output_filename = str(
                result.output_path.relative_to(book_dir(book_id))
            )
        except ValueError:
            # Output path is not under the book workspace — surface as-is.
            output_filename = str(result.output_path)

    return TranslateNextResponseModel(
        book_id=result.book_id,
        ran_index=result.ran_index,
        success=result.success,
        chapter_status=chapter_status,
        error_message=result.error_message,
        output_filename=output_filename,
        book=detail,
    )


if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8000)
