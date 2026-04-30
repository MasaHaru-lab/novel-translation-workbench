import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..'))

import pytest

from app.translate.project_context import (
    ASSET_NAMES,
    PROMPT_NAMES,
    load_all_assets,
    load_asset,
    load_prompt,
)


def test_load_prompts_return_nonempty_text():
    for name in PROMPT_NAMES:
        text = load_prompt(name)
        assert isinstance(text, str)
        assert text.strip(), f"Prompt {name} is empty"


def test_load_prompt_unknown_name_raises():
    with pytest.raises(ValueError):
        load_prompt("prompt_z")


def test_load_all_assets_returns_every_known_name():
    assets = load_all_assets()
    assert set(assets.keys()) == set(ASSET_NAMES)


def test_each_known_asset_resolves_on_disk():
    for name in ASSET_NAMES:
        text = load_asset(name)
        assert text is not None, f"Asset {name} not found on disk"
        assert text.strip(), f"Asset {name} is empty"


def test_load_asset_unknown_name_raises():
    with pytest.raises(ValueError):
        load_asset("nonexistent_asset")


def _collect_note_values(text: str) -> list:
    """Extract note values from an asset file's markdown structure.

    Looks for lines beginning with ``- Notes:`` and collects their content,
    including continuation lines (indented subsequent lines).
    """
    notes = []
    lines = text.splitlines()
    i = 0
    while i < len(lines):
        line = lines[i]
        stripped = line.strip()
        if stripped.startswith("- Notes:"):
            # Collect the note value, which may span continuation lines.
            note = stripped[len("- Notes:"):].strip()
            i += 1
            while i < len(lines):
                cont = lines[i].strip()
                # Continuation: starts with - or begins a new list item
                if cont.startswith("- ") and not cont.startswith("- Notes:"):
                    break
                if cont and not cont.startswith("- "):
                    # Not a new list item; could be continuation or a new heading.
                    # Halt if it looks like a heading or blank.
                    if cont.startswith("#") or cont.startswith("###"):
                        break
                    if not cont:
                        i += 1
                        break
                    note += " " + cont
                    i += 1
                else:
                    break
            notes.append(note)
        else:
            i += 1
    return notes


_EDITORIAL_INDICATORS = [
    ":",        # Instructional framing / key-value structure
    "Keep", "Preserve", "Do not", "Prefer",
    "Provisional", "Means", "In context", "Translate",
    "For now", "Ritual term", "Historical", "Fictional",
    "Related to", "Context-sensitive", "May use",
    "Current working", "UNRESOLVED", "HIGH RISK",
    # Character/role descriptions — metadata, not prose content
    "in the Qin", "in the family", "in the household",
    "of the Qin", "of the family",
    # Descriptive role patterns
    "matriarch", "figure in",
]


def _is_editorial_note(note: str) -> bool:
    """Return True if the note text looks like editorial/instructional content,
    not like prose text that could leak into a translation."""
    if not note:
        return False
    # Multi-sentence or long notes are clearly editorial.
    if len(note) > 120:
        return True
    # Contains a code span (markdown backtick).
    if "`" in note:
        return True
    # Contains an editorial keyword.
    lower = note.lower()
    for indicator in _EDITORIAL_INDICATORS:
        if indicator.lower() in lower:
            return True
    return False


def test_asset_notes_are_editorial_not_prose():
    """Project asset note fields must contain editorial/instructional content,
    not bare prose phrases that could leak into translated output.

    A note value like "context-dependent; see notes" is indistinguishable from
    prose and risks being rendered into the final translation. Notes must
    contain instructional framing, editorial keywords, or be long enough that
    prose ambiguity is unlikely.
    """
    failures = []
    for name in ASSET_NAMES:
        text = load_asset(name)
        if not text or not text.strip():
            continue
        notes = _collect_note_values(text)
        for note in notes:
            if not _is_editorial_note(note):
                failures.append(f"  {name}: {note!r}")

    assert not failures, (
        "Project assets contain note values that look like prose content and "
        "could leak into translated output. All notes must be editorial/"
        "instructional in nature:\n" + "\n".join(failures)
    )


@pytest.mark.parametrize("bad_value", [
    "context-dependent; see notes",
    "context-dependent; see notes.",
    "Context-dependent; see notes",
    "context dependent; see notes",
])
def test_asset_notes_reject_specific_degenerate_pattern(bad_value):
    """The specific degenerate pattern 'context-dependent; see notes' must
    never appear in any asset field. This was the root of a prior leak where
    the model rendered the note field literal into the final prose."""
    for name in ASSET_NAMES:
        text = load_asset(name)
        if text and bad_value in text:
            pytest.fail(f"Asset {name} contains degenerate note pattern: {bad_value!r}")


_RESOLVED_RENDERINGS = {
    "Xi’er": ["girl", "Little Xi"],
    "legal mother": ["principal mother"],
}


def test_resolved_term_renderings():
    """丫头/西丫头 → Xi’er; 嫡母 → legal mother. Rejected forms must not appear as the canonical rendering value."""
    text = load_asset("titles_and_terms")
    for canonical, rejected_list in _RESOLVED_RENDERINGS.items():
        assert f"Working English rendering: {canonical}" in text, \
            f"Expected canonical rendering {canonical!r} not found in titles_and_terms"
        for rejected in rejected_list:
            assert f"Working English rendering: {rejected}" not in text, \
                f"Rejected rendering {rejected!r} found as a Working English rendering in titles_and_terms"
