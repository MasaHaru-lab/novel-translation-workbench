"""Read-only loader for translation prompts and project assets.

Provides a single place for code to access the governed prompt files
(prompts/prompt_a.md, prompts/prompt_b.md) and project assets
(project_assets/characters.md, glossary.md, titles_and_terms.md,
style_notes.md, unresolved_decisions.md) that are declared in
CLAUDE.md / WORKFLOW.md / SKILL.md.

This module is intentionally minimal and read-only. No writeback, no
parsing, no caching beyond what the filesystem provides.
"""

from pathlib import Path
from typing import Dict, Optional


REPO_ROOT = Path(__file__).resolve().parents[2]
PROMPTS_DIR = REPO_ROOT / "prompts"
ASSETS_DIR = REPO_ROOT / "project_assets"

PROMPT_NAMES = ("prompt_a", "prompt_b")
ASSET_NAMES = (
    "characters",
    "titles_and_terms",
    "glossary",
    "style_notes",
    "unresolved_decisions",
)


def _find_asset_file(name: str) -> Optional[Path]:
    """Locate an asset file by canonical name.

    Accepts the canonical filename (e.g. ``glossary.md``) and also tolerates
    the ordered-prefix variants currently on disk (``1. glossary.md``).
    """
    direct = ASSETS_DIR / f"{name}.md"
    if direct.is_file():
        return direct
    matches = sorted(ASSETS_DIR.glob(f"*{name}.md"))
    return matches[0] if matches else None


def load_prompt(name: str) -> str:
    """Return the raw text of a prompt file (prompt_a / prompt_b)."""
    if name not in PROMPT_NAMES:
        raise ValueError(f"Unknown prompt: {name!r}. Expected one of {PROMPT_NAMES}.")
    path = PROMPTS_DIR / f"{name}.md"
    if not path.is_file():
        raise FileNotFoundError(f"Prompt file not found: {path}")
    return path.read_text(encoding="utf-8")


def load_asset(name: str) -> Optional[str]:
    """Return the raw text of a project asset, or None if not present."""
    if name not in ASSET_NAMES:
        raise ValueError(f"Unknown asset: {name!r}. Expected one of {ASSET_NAMES}.")
    path = _find_asset_file(name)
    if path is None:
        return None
    return path.read_text(encoding="utf-8")


def load_all_assets() -> Dict[str, Optional[str]]:
    """Return every known project asset keyed by canonical name."""
    return {name: load_asset(name) for name in ASSET_NAMES}
