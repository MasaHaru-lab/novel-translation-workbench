"""Bootstrap a BookMemory from existing project_assets markdown files.

This is a one-time or occasional import path: it reads the flat
``project_assets/*.md`` files that the consistency auditor already
uses and produces structured ``BookEntity``, ``TitleRecord``,
``TranslationDecision``, and ``UnresolvedDecision`` records.

The bootstrap is intentionally conservative: it does not attempt to
infer relationships, tags, or descriptions from the asset files since
those are richer and require human judgement. What it produces is a
minimal, validated BookMemory that can be edited and extended.

Call ``bootstrap_from_project_assets()`` to get a populated ``BookMemory``.
"""

import re
from typing import Dict, List, Optional

from app.book_memory.models import (
    EntityType,
    MemoryRecordStatus,
    EvidenceRef,
    BookEntity,
    TitleRecord,
    TranslationDecision,
    UnresolvedDecision,
    BookMemory,
)
from app.translate.project_context import load_asset


# ── Parser helpers (asset file → structured records) ────────────────────────


_RENDERING_RE = re.compile(
    r"(?:Working )?English rendering\s*:\s*(.+?)$", re.IGNORECASE | re.MULTILINE
)
_NOTES_RE = re.compile(r"- Notes\s*:\s*(.+)", re.IGNORECASE)


def _split_sections(text: str) -> List[tuple]:
    """Split a markdown file into ``### heading`` sections.

    Returns list of (heading_text, section_body) tuples.
    """
    sections: List[tuple] = []
    for section in re.split(r"^### ", text, flags=re.MULTILINE):
        section = section.strip()
        if not section:
            continue
        lines = section.splitlines()
        heading = lines[0].strip()
        body = "\n".join(lines[1:]) if len(lines) > 1 else ""
        sections.append((heading, body))
    return sections


def _extract_rendering(text: str) -> Optional[str]:
    """Extract the English rendering from a section body."""
    m = _RENDERING_RE.search(text)
    if m:
        return m.group(1).strip()
    return None


def _extract_notes(text: str) -> str:
    """Extract the Notes line from a section body."""
    m = _NOTES_RE.search(text)
    if m:
        return m.group(1).strip()
    return ""


def _extract_chinese(text: str) -> str:
    """Extract Chinese line (e.g. ``- Chinese: 秦流西``) from a section body."""
    m = re.search(r"- Chinese\s*:\s*(.+)", text, re.IGNORECASE)
    if m:
        return m.group(1).strip()
    return ""


def _make_entity_id(name_en: str) -> str:
    """Generate a stable entity id from an English rendering."""
    return name_en.lower().replace(" ", "_").replace("'", "").replace("(", "").replace(")", "").replace("/", "_")


# ── Characters → BookEntity ─────────────────────────────────────────────────


def bootstrap_entities(asset_text: str) -> Dict[str, BookEntity]:
    """Parse characters.md into BookEntity dict."""
    entities: Dict[str, BookEntity] = {}
    for heading, body in _split_sections(asset_text):
        rendering = _extract_rendering(body)
        if not rendering:
            continue
        name_zh = _extract_chinese(body)
        notes = _extract_notes(body)
        eid = _make_entity_id(rendering)

        entities[eid] = BookEntity(
            id=eid,
            name_zh=name_zh or heading,
            name_en=rendering,
            entity_type=EntityType.CHARACTER,
            description=notes,
            status=MemoryRecordStatus.TENTATIVE,
        )
    return entities


# ── Titles / Terms → TitleRecord ────────────────────────────────────────────


def _bootstrap_titles(
    asset_text: str, category: str
) -> Dict[str, TitleRecord]:
    """Parse a title/term asset file into TitleRecord dict."""
    records: Dict[str, TitleRecord] = {}
    for heading, body in _split_sections(asset_text):
        rendering = _extract_rendering(body)
        if not rendering:
            continue
        name_zh = _extract_chinese(body)
        notes = _extract_notes(body)
        tid = _make_entity_id(rendering)

        records[tid] = TitleRecord(
            id=tid,
            name_zh=name_zh or heading,
            name_en=rendering,
            category=category,
            notes=notes,
            status=MemoryRecordStatus.TENTATIVE,
        )
    return records


# ── Unresolved decisions → UnresolvedDecision / TranslationDecision ─────────


def _split_subsections(text: str, subsection_marker: str = "###") -> Dict[str, str]:
    """Split a file by subsection headings within the full text.

    Returns dict mapping heading (text after the marker) to subsection body.
    The regex anchors at line start and escapes the marker for safe use.
    """
    safe = re.escape(subsection_marker)
    pattern = rf"^{safe} "
    sections: Dict[str, str] = {}
    for section in re.split(pattern, text, flags=re.MULTILINE):
        section = section.strip()
        if not section:
            continue
        lines = section.splitlines()
        heading = lines[0].strip()
        body = "\n".join(lines[1:]) if len(lines) > 1 else ""
        sections[heading] = body
    return sections


def bootstrap_decisions(
    asset_text: str,
) -> tuple:
    """Parse unresolved_decisions.md into (decisions, unresolved) dicts.

    Returns:
        (translation_decisions_dict, unresolved_decisions_dict)
    """
    decisions: Dict[str, TranslationDecision] = {}
    unresolved: Dict[str, UnresolvedDecision] = {}

    # Resolved-item rendering: "- Resolution: rendered as `value`" or "- Resolution: value"
    _RESOLUTION_RE = re.compile(
        r"- Resolution\s*:\s*(?:rendered as\s+)?(`?)([^`\n]+)\1",
        re.IGNORECASE,
    )

    # Split into top-level sections: "Open items", "Resolved items"
    top_sections = _split_subsections(asset_text, subsection_marker="##")

    # Parse "Open items"
    open_text = top_sections.get("Open items", "")
    if open_text:
        for heading, body in _split_sections(open_text):
            uid = _make_entity_id(heading)
            notes = _extract_notes(body)

            unresolved[uid] = UnresolvedDecision(
                id=uid,
                question=heading,
                options=[],
                recommendation=notes,
                status=MemoryRecordStatus.UNRESOLVED,
                created_chapter=0,
            )

    # Parse "Resolved items"
    resolved_text = top_sections.get("Resolved items", "")
    if resolved_text:
        for heading, body in _split_sections(resolved_text):
            # Use "Resolution:" line for the rendering value
            resolution_match = _RESOLUTION_RE.search(body)
            rendering = resolution_match.group(2).strip() if resolution_match else _extract_rendering(body)
            did = _make_entity_id(rendering) if rendering else _make_entity_id(heading)

            # Extract rationale
            rationale_match = re.search(r"- Rationale\s*:\s*(.+)", body, re.IGNORECASE)
            rationale = rationale_match.group(1).strip() if rationale_match else ""

            decisions[did] = TranslationDecision(
                id=did,
                entity_id=did,
                decision_type="rendering",
                new_value=rendering or "",
                rationale=rationale or "",
                status=MemoryRecordStatus.TENTATIVE,
                chapter_decided=0,
            )

    return decisions, unresolved


# ── Main bootstrap entry point ──────────────────────────────────────────────


def bootstrap_from_project_assets() -> BookMemory:
    """Load project_assets and build a structured BookMemory.

    Combines data from:
    - characters.md → entities (BookEntity)
    - titles_and_terms.md → titles (TitleRecord)
    - glossary.md → titles (TitleRecord with category="term")
    - unresolved_decisions.md → translation_decisions + unresolved_decisions

    Returns a BookMemory with all extracted records. Empty sections are
    simply absent from their respective dicts.
    """
    memory = BookMemory()

    # Characters → entities
    chars_text = load_asset("characters") or ""
    memory.entities = bootstrap_entities(chars_text)

    # Titles → TitleRecord dict
    titles_text = load_asset("titles_and_terms") or ""
    memory.titles.update(_bootstrap_titles(titles_text, "title"))

    # Glossary → TitleRecord dict (category="term")
    glossary_text = load_asset("glossary") or ""
    memory.titles.update(_bootstrap_titles(glossary_text, "term"))

    # Decisions
    decisions_text = load_asset("unresolved_decisions") or ""
    decisions, unresolved = bootstrap_decisions(decisions_text)
    memory.translation_decisions = decisions
    memory.unresolved_decisions = unresolved

    return memory
