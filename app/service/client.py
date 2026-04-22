"""
HTTP client for translation service.
"""
import json
import logging
from typing import Optional
from dataclasses import asdict

try:
    import requests
    REQUESTS_AVAILABLE = True
except ImportError:
    REQUESTS_AVAILABLE = False

from app.translate.schema import TranslationInput, TranslationOutput, GlossaryTerm
from app.config import config


logger = logging.getLogger(__name__)


class TranslationServiceClient:
    """Client for translation HTTP service."""

    def __init__(self, base_url: Optional[str] = None):
        if not REQUESTS_AVAILABLE:
            raise RuntimeError(
                "Requests library is not installed. "
                "Please install 'requests' to use the HTTP client."
            )
        self.base_url = base_url or config.BASE_URL

    def translate_draft(self, input: TranslationInput) -> TranslationOutput:
        """Send translation request to the service."""
        url = f"{self.base_url.rstrip('/')}/translate/draft"
        # Convert input to JSON-serializable dict
        payload = {
            "segment_id": input.segment_id,
            "source_text": input.source_text,
            "prev_context": input.prev_context,
            "next_context": input.next_context,
            "glossary_terms": [{"zh": term.zh, "en": term.en} for term in input.glossary_terms]
        }
        try:
            response = requests.post(url, json=payload, timeout=30)
            response.raise_for_status()
            data = response.json()
            # Convert back to TranslationOutput
            return TranslationOutput(
                segment_id=data["segment_id"],
                draft_translation=data["draft_translation"],
                polished_translation=data["polished_translation"],
                notes=data.get("notes", [])
            )
        except requests.exceptions.ConnectionError:
            logger.error(f"Could not connect to translation service at {url}")
            raise
        except requests.exceptions.Timeout:
            logger.error("Request to translation service timed out")
            raise
        except Exception as e:
            logger.error(f"Translation service request failed: {e}")
            raise


# Singleton client instance
_client_instance: Optional[TranslationServiceClient] = None


def get_client() -> TranslationServiceClient:
    """Get singleton translation service client."""
    global _client_instance
    if _client_instance is None:
        _client_instance = TranslationServiceClient()
    return _client_instance


def translate_draft_via_http(input: TranslationInput) -> TranslationOutput:
    """Convenience function to translate via HTTP service."""
    client = get_client()
    return client.translate_draft(input)