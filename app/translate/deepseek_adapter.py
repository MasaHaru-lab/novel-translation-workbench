"""DeepSeek / OpenAI-compatible chat-completion adapter.

Builds ``chat/completions`` style requests and extracts the response
from ``choices[0].message.content``.

Compatible with any provider that exposes an OpenAI-compatible
completions API (DeepSeek, OpenAI, Together, Groq, etc.).
"""
from __future__ import annotations

import json
import logging
from typing import Optional

try:
    import requests

    REQUESTS_AVAILABLE = True
except ImportError:
    REQUESTS_AVAILABLE = False

from app.translate.model_profiles import ModelProfile, resolve_base_url, resolve_api_key

logger = logging.getLogger(__name__)


def call_chat_completion(
    profile: ModelProfile,
    prompt: str,
    model: Optional[str] = None,
    max_tokens: Optional[int] = None,
) -> str:
    """Call an OpenAI-compatible chat completion API and return the response text.

    Args:
        profile:   The model profile to use for resolving URL, key, and model.
        prompt:    The prompt text to send as the user message.
        model:     Override the profile's default model. Falls back to
                   ``profile.default_model`` when None.
        max_tokens: Optional max tokens for the response.

    Returns:
        The extracted response text from ``choices[0].message.content``.

    Raises:
        RuntimeError: On connection failure, timeout, HTTP error,
                      missing API key, or malformed response.
    """
    if not REQUESTS_AVAILABLE:
        raise RuntimeError("requests library not installed; install with 'pip install requests'")

    base_url = resolve_base_url(profile)
    api_key = resolve_api_key(profile)
    model_name = model or profile.default_model

    if not model_name:
        raise RuntimeError(
            f"Profile {profile.name!r} has no default_model set "
            f"and no --model override was provided"
        )

    # Build chat/completions URL
    url = base_url.rstrip("/") + "/chat/completions"

    messages = [{"role": "user", "content": prompt}]
    body = {"model": model_name, "messages": messages}
    if max_tokens is not None:
        body["max_tokens"] = max_tokens

    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {api_key}",
    }

    try:
        response = requests.post(url, json=body, headers=headers, timeout=60)
        response.raise_for_status()
    except requests.exceptions.ConnectionError as e:
        logger.error("Chat completion connection failed: %s", e)
        raise RuntimeError(f"Chat completion connection failed: {e}")
    except requests.exceptions.Timeout as e:
        logger.error("Chat completion request timed out")
        raise RuntimeError(f"Chat completion timeout: {e}")
    except requests.exceptions.RequestException as e:
        logger.error("Chat completion request failed: %s", e)
        raise RuntimeError(f"Chat completion request error: {e}")

    try:
        data = response.json()
    except json.JSONDecodeError as e:
        logger.error("Chat completion returned invalid JSON: %s", response.text[:200])
        raise RuntimeError(f"Chat completion returned invalid JSON: {e}")

    try:
        text = data["choices"][0]["message"]["content"]
    except (KeyError, IndexError, TypeError) as e:
        logger.error(
            "Chat completion response missing choices[0].message.content: %s", data
        )
        raise RuntimeError(
            f"Chat completion response missing expected content field: {e}"
        )

    if not isinstance(text, str):
        text = str(text)

    return text.strip()
