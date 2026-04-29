"""Model profile registry for backend-owned model configuration.

Profiles define which provider, base URL, and model to use for translation.
Secrets are referenced by env var name only — never stored or logged as values.
"""
from __future__ import annotations

import os
from dataclasses import dataclass, field
from typing import Optional


@dataclass(frozen=True)
class ModelProfile:
    """A named model configuration with env-var-based secret references.

    Fields:
        name:         Unique profile identifier used for CLI selection.
        provider:     Adapter type — ``"prompt-http"`` for the legacy
                      prompt-only request contract, ``"openai-compat"`` for
                      chat-completions-style requests.
        api_base_env: Name of the env var holding the API base URL.
        api_key_env:  Name of the env var holding the API key, or None for
                      local backends that do not require authentication.
        default_model: Default model identifier for chat-completion profiles,
                       or None for prompt-http profiles.
    """

    name: str
    provider: str
    api_base_env: str
    api_key_env: Optional[str] = None
    default_model: Optional[str] = None


# ── Built-in profiles ──────────────────────────────────────────────────────

LOCAL_QWEN = ModelProfile(
    name="local-qwen",
    provider="prompt-http",
    api_base_env="MODEL_BACKEND_URL",
    api_key_env=None,
    default_model=None,
)

DEEPSEEK_V4_FLASH = ModelProfile(
    name="deepseek-v4-flash",
    provider="openai-compat",
    api_base_env="DEEPSEEK_BASE_URL",
    api_key_env="DEEPSEEK_API_KEY",
    default_model="deepseek-chat",
)

DEEPSEEK_V4_PRO = ModelProfile(
    name="deepseek-v4-pro",
    provider="openai-compat",
    api_base_env="DEEPSEEK_BASE_URL",
    api_key_env="DEEPSEEK_API_KEY",
    default_model="deepseek-reasoner",
)

# ── Registry ───────────────────────────────────────────────────────────────

_REGISTRY: dict[str, ModelProfile] = {
    p.name: p for p in [LOCAL_QWEN, DEEPSEEK_V4_FLASH, DEEPSEEK_V4_PRO]
}


def get_profile(name: str) -> ModelProfile:
    """Look up a profile by name. Raises KeyError on unknown name."""
    if name not in _REGISTRY:
        known = ", ".join(sorted(_REGISTRY))
        raise KeyError(f"Unknown model profile {name!r}. Known profiles: {known}")
    return _REGISTRY[name]


def list_profiles() -> dict[str, ModelProfile]:
    """Return a copy of the profile registry."""
    return dict(_REGISTRY)


def resolve_base_url(profile: ModelProfile) -> str:
    """Resolve the API base URL from the environment for the given profile."""
    url = os.environ.get(profile.api_base_env, "").strip()
    if not url:
        raise RuntimeError(
            f"Profile {profile.name!r} requires {profile.api_base_env} "
            f"to be set in the environment or .env.local"
        )
    return url


def resolve_api_key(profile: ModelProfile) -> Optional[str]:
    """Resolve the API key from the environment for the given profile.

    Returns None when the profile does not require authentication
    (api_key_env is None).
    """
    if profile.api_key_env is None:
        return None
    key = os.environ.get(profile.api_key_env, "").strip()
    if not key:
        raise RuntimeError(
            f"Profile {profile.name!r} requires {profile.api_key_env} "
            f"to be set in the environment or .env.local"
        )
    return key
