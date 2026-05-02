"""Environment config loader for backend-owned secrets.

Reads ``.env.local`` from the project root and loads each KEY=VALUE line
into ``os.environ`` so that model profile resolution can find secrets
such as API keys.

Usage:

    from app.config_loader import load_env_local
    load_env_local()

This is safe to call multiple times — subsequent calls are no-ops
(a ``_loaded`` flag prevents duplicate parsing).

The loader is intentionally *not* auto-imported by ``app.config`` or
``app.translate.model_profiles`` so that callers (CLI, service, tests)
explicitly opt in to local secret loading.
"""
from __future__ import annotations

import os
from pathlib import Path

_loaded: bool = False


def find_project_root() -> Path:
    """Detect the project root directory.

    Walks up from ``app/config_loader.py`` looking for known project markers
    (``.git`` directory, ``.env.example`` file). This avoids the earlier bug
    of scanning for ``.env.local`` (which does not exist until the operator
    creates it) and falling back to the wrong directory (``app/``).
    """
    here = Path(__file__).resolve().parent  # e.g. …/novel-translation-workbench/app/
    for parent in [here] + list(here.parents):
        if (parent / ".git").is_dir():
            return parent
        if (parent / ".env.example").is_file():
            return parent
    # Fallback: parent of app/ is the project root
    return here.parent


def load_env_local(project_root: str | Path | None = None) -> None:
    """Load ``.env.local`` into ``os.environ`` (idempotent).

    Args:
        project_root: Explicit project root path. When None, auto-detect
                      by walking up from this script's location.
    """
    global _loaded
    if _loaded:
        return

    if project_root is not None:
        root = Path(project_root).resolve()
    else:
        root = find_project_root()

    env_path = root / ".env.local"
    if not env_path.exists():
        _loaded = True
        return

    with open(env_path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            # Skip blank lines and comments
            if not line or line.startswith("#"):
                continue
            if "=" not in line:
                continue
            key, _, value = line.partition("=")
            key = key.strip()
            value = value.strip().strip("\"'")
            # Only set if not already present (env var takes precedence)
            if key not in os.environ:
                os.environ[key] = value

    _loaded = True
