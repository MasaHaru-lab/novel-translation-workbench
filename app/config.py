"""
Simple configuration for translation service and model backend.
"""
import os


class TranslationServiceConfig:
    """Configuration for translation service client."""

    # Base URL for the translation service, can be overridden by environment variable
    BASE_URL = os.getenv("TRANSLATION_SERVICE_URL", "http://localhost:8000")

    # Model backend URL for real translation (e.g., http://localhost:11434/api/generate)
    MODEL_BACKEND_URL = os.getenv("MODEL_BACKEND_URL", "")

    # Timeout for model backend requests in seconds
    MODEL_TIMEOUT_SECONDS = int(os.getenv("MODEL_TIMEOUT_SECONDS", "30"))


# Singleton instance
config = TranslationServiceConfig()