"""
FastAPI service for draft translation.

Exposes a single endpoint POST /translate/draft that calls a local model backend.
"""
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from typing import List, Optional
import uvicorn

from app.translate.schema import TranslationInput, TranslationOutput, GlossaryTerm
from app.translate.backend_adapter import translate_draft_with_backend
from app.config import config


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


@app.get("/health")
async def health():
    """Health check endpoint."""
    return {"status": "healthy"}


if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8000)