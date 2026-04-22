"""
Adapter for calling a local model backend HTTP endpoint for draft translation.
"""
import json
import logging
from typing import Optional

try:
    import requests
    REQUESTS_AVAILABLE = True
except ImportError:
    REQUESTS_AVAILABLE = False

from app.translate.schema import TranslationInput, TranslationOutput, GlossaryTerm
from app.config import config

logger = logging.getLogger(__name__)


def build_draft_prompt(
    input: TranslationInput,
    assets_mode: "str" = "full",
) -> str:
    """Build a prompt for faithful draft translation.

    Delegates to ``app.translate.translator.build_draft_prompt`` so the
    service/backend draft path uses the same prompt-file + project-asset
    model as the local pipeline path.
    """
    from app.translate.translator import build_draft_prompt as _unified
    return _unified(input, assets_mode)


def call_model_backend(prompt: str, max_tokens: Optional[int] = None, **extra) -> str:
    """Send prompt to model backend and return plain text response.

    Assumes backend endpoint expects JSON with "prompt" field and returns JSON with "text" field.
    This is compatible with Ollama's /api/generate and similar llama.cpp completions.

    If max_tokens is provided, adds both "max_tokens" and "completion" fields to the request JSON.
    Additional keyword arguments are merged into the request JSON (e.g., model="...", stream=False).

    Raises:
        RuntimeError: if MODEL_BACKEND_URL not configured, request fails, or response malformed.
    """
    if not REQUESTS_AVAILABLE:
        raise RuntimeError("requests library not installed; install with 'pip install requests'")
    backend_url = config.MODEL_BACKEND_URL.strip()
    if not backend_url:
        raise RuntimeError("MODEL_BACKEND_URL not configured")

    payload = {"prompt": prompt}
    if max_tokens is not None:
        payload["max_tokens"] = max_tokens
        payload["completion"] = max_tokens
    if extra:
        payload.update(extra)
    timeout = config.MODEL_TIMEOUT_SECONDS

    try:
        response = requests.post(backend_url, json=payload, timeout=timeout)
        response.raise_for_status()
    except requests.exceptions.ConnectionError as e:
        logger.error(f"Could not connect to model backend at {backend_url}: {e}")
        raise RuntimeError(f"Model backend connection failed: {e}")
    except requests.exceptions.Timeout as e:
        logger.error(f"Model backend request timed out after {timeout}s")
        raise RuntimeError(f"Model backend timeout: {e}")
    except requests.exceptions.RequestException as e:
        logger.error(f"Model backend request failed: {e}")
        raise RuntimeError(f"Model backend request error: {e}")

    # Parse response JSON
    try:
        data = response.json()
    except json.JSONDecodeError as e:
        logger.error(f"Model backend returned invalid JSON: {response.text[:200]}")
        raise RuntimeError(f"Model backend returned invalid JSON: {e}")

    # Extract text field; adapt based on known backend structures
    if "text" in data:
        text = data["text"]
    elif "response" in data:
        text = data["response"]
    elif "generated_text" in data:
        text = data["generated_text"]
    elif "content" in data:
        text = data["content"]
    elif "choices" in data and isinstance(data["choices"], list) and len(data["choices"]) > 0:
        choice = data["choices"][0]
        if "message" in choice and isinstance(choice["message"], dict) and "content" in choice["message"]:
            text = choice["message"]["content"]
        elif "text" in choice:
            text = choice["text"]
        elif "content" in choice:
            text = choice["content"]
        else:
            logger.error(f"Unsupported choice structure: {choice}")
            raise RuntimeError("Model backend response missing text field")
    else:
        # If the response is just a plain string, assume it's the translation
        if isinstance(data, str):
            text = data
        else:
            logger.error(f"Model backend response missing known text field: {data}")
            raise RuntimeError("Model backend response missing text field")

    # Ensure we have a string
    if not isinstance(text, str):
        text = str(text)

    # Strip leading/trailing whitespace
    return text.strip()


def translate_draft_with_backend(
    input: TranslationInput,
    assets_mode: "str" = "full",
) -> TranslationOutput:
    """Generate a faithful draft translation using the configured model backend.

    Uses the unified prompt builder and project-asset model shared with the
    local pipeline path (``app.translate.translator.build_draft_prompt``),
    so prompt-file content and asset injection behave consistently whether
    the caller is the local pipeline or the HTTP service.

    ``assets_mode`` mirrors the translator-layer contract: ``"full"``
    (default) injects project assets; ``"none"`` suppresses asset injection.
    The public HTTP surface does not expose this parameter; callers that
    want to override it do so internally.

    Returns:
        TranslationOutput with draft_translation from model, polished_translation empty,
        and optional notes about backend metadata.

    Raises:
        RuntimeError: if backend call fails.
        ValueError: if assets_mode is not a recognized value.
    """
    from app.translate.translator import (
        build_draft_prompt as _build_draft_prompt,
        clean_draft_output,
        apply_glossary,
        DRAFT_MAX_TOKENS,
    )

    prompt = _build_draft_prompt(input, assets_mode)

    draft_text = call_model_backend(prompt, max_tokens=DRAFT_MAX_TOKENS)

    draft_text = clean_draft_output(draft_text)

    if input.glossary_terms:
        draft_text = apply_glossary(draft_text, input.glossary_terms)

    return TranslationOutput(
        segment_id=input.segment_id,
        draft_translation=draft_text,
        polished_translation="",
        notes=[f"Backend: {config.MODEL_BACKEND_URL}"]
    )