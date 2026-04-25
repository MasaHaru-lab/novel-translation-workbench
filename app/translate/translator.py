from typing import List, Literal, Optional
from dataclasses import dataclass, field
import logging
import re
from .schema import TranslationInput, TranslationOutput, GlossaryTerm
from .project_context import ASSET_NAMES, load_all_assets, load_prompt
from app.segment.segmenter import Segment

logger = logging.getLogger(__name__)


AssetsMode = Literal["full", "none"]
ASSETS_MODES: tuple[AssetsMode, ...] = ("full", "none")
DEFAULT_ASSETS_MODE: AssetsMode = "full"

# ── Budget profile (Batch 4B) ─────────────────────────────────────────────


@dataclass
class BudgetConfig:
    """Token budget configuration derived from a budget profile.

    These are safety caps for max_tokens per step (completion tokens).
    The backend's context window is the real bound; these limits prevent
    runaway generation or backend request failure.
    """

    draft_max_tokens: int = 4096
    review_max_tokens: int = 2048
    polish_max_tokens: int = 4096


# Budget profile → BudgetConfig mapping (Batch 4B enactment)
BUDGET_PROFILES = {
    "light": BudgetConfig(
        draft_max_tokens=2048,
        review_max_tokens=1024,
        polish_max_tokens=2048,
    ),
    "standard": BudgetConfig(
        draft_max_tokens=4096,
        review_max_tokens=2048,
        polish_max_tokens=4096,
    ),
    "conservative": BudgetConfig(
        draft_max_tokens=6144,
        review_max_tokens=3072,
        polish_max_tokens=6144,
    ),
}


def resolve_budget_config(profile: str) -> BudgetConfig:
    """Resolve a budget profile name to a concrete BudgetConfig.

    Args:
        profile: "light", "standard", or "conservative".
            Unknown values fall back to "standard".

    Returns:
        BudgetConfig with appropriate token caps.
    """
    return BUDGET_PROFILES.get(profile, BUDGET_PROFILES["standard"])


# Legacy constants kept for backward compatibility
DRAFT_MAX_TOKENS = 4096
REVIEW_MAX_TOKENS = 2048
POLISH_MAX_TOKENS = 4096


def _validate_assets_mode(mode: str) -> AssetsMode:
    if mode not in ASSETS_MODES:
        raise ValueError(
            f"Unknown assets_mode: {mode!r}. Expected one of {ASSETS_MODES}."
        )
    return mode  # type: ignore[return-value]


def translate_draft(
    input: TranslationInput,
    assets_mode: AssetsMode = DEFAULT_ASSETS_MODE,
    budget_config: Optional[BudgetConfig] = None,
) -> TranslationOutput:
    """Generate a faithful draft translation of the segment text using model backend.

    Requires MODEL_BACKEND_URL to be configured.
    Calls model backend with a draft prompt to get a real translation.

    See ``build_project_assets_block`` for ``assets_mode`` semantics.

    Raises:
        RuntimeError: if MODEL_BACKEND_URL not configured or backend call fails.
        ValueError: if assets_mode is not a recognized value.
    """
    _validate_assets_mode(assets_mode)
    # Import inside function to avoid hiding import errors at module level
    try:
        from app.config import config
        from app.translate.backend_adapter import call_model_backend
    except ImportError as e:
        raise RuntimeError(
            f"Backend draft translation requested but required dependencies not available: {e}. "
            f"Install required dependencies (e.g., 'pip install requests')."
        ) from e

    # Check if backend URL is configured
    if not config.MODEL_BACKEND_URL or not config.MODEL_BACKEND_URL.strip():
        raise RuntimeError(
            "MODEL_BACKEND_URL not configured. Draft translation requires a real backend. "
            "Set MODEL_BACKEND_URL environment variable to enable draft step."
        )

    # Backend configured: attempt real draft translation
    prompt = build_draft_prompt(input, assets_mode)
    bc = budget_config or BudgetConfig()
    try:
        draft_text = call_model_backend(prompt, max_tokens=bc.draft_max_tokens)
    except Exception as e:
        raise RuntimeError(f"Backend draft call failed: {e}") from e

    # Clean potential prefix shell
    draft_text = clean_draft_output(draft_text)

    # Apply glossary replacement (safety measure, backend should already respect glossary)
    if input.glossary_terms:
        draft_text = apply_glossary(draft_text, input.glossary_terms)

    return TranslationOutput(
        segment_id=input.segment_id,
        draft_translation=draft_text,
        polished_translation="",
        notes=[]
    )


def polish_translation(
    input: TranslationInput,
    draft_output: TranslationOutput,
    assets_mode: AssetsMode = DEFAULT_ASSETS_MODE,
    budget_config: Optional[BudgetConfig] = None,
) -> TranslationOutput:
    """Run the default A → B → revise-if-needed workflow on a draft.

    Per WORKFLOW.md:
      * Step 2 — run one internal Prompt B review pass on the draft
      * Step 3 — if the review reports a major issue, run one Prompt A-based
        revision pass using the review finding as guidance
      * Step 4 — return prose only; reviewer scaffolding is never exposed

    When the reviewer reports no major issue, the draft is already considered
    final prose and is returned unchanged as the polished output.

    See ``build_project_assets_block`` for ``assets_mode`` semantics.

    Raises:
        RuntimeError: if MODEL_BACKEND_URL not configured or backend call fails.
        ValueError: if assets_mode is not a recognized value.
    """
    _validate_assets_mode(assets_mode)
    draft_text = draft_output.draft_translation
    bc = budget_config or BudgetConfig()

    # Step 1 — internal review (Prompt B). Output stays internal.
    review_raw = run_internal_review_with_backend(input, draft_text, assets_mode, budget_config=bc)
    findings = parse_review_findings(review_raw)

    # Step 1.5 — coverage gate: catch omissions Prompt B may have missed.
    # Runs after review but before the revision decision.  If the gate
    # fires and Prompt B did not already flag a major issue, inject the
    # coverage finding to trigger the existing revision path.
    coverage_finding = check_segment_coverage(input.source_text, draft_text)
    if coverage_finding and not findings.has_major_issue():
        findings = coverage_finding

    # Step 2 — revise once if a material issue was flagged, else keep draft.
    if findings.has_major_issue():
        polished_text = translate_polish_with_backend(
            input, draft_text, assets_mode, review_guidance=findings, budget_config=bc
        )
    else:
        polished_text = draft_text

    # Glossary safety net (backend should already respect glossary).
    if input.glossary_terms:
        polished_text = apply_glossary(polished_text, input.glossary_terms)

    # Final safety net: reviewer scaffolding must never reach default output.
    polished_text = clean_polished_output(polished_text)

    return TranslationOutput(
        segment_id=input.segment_id,
        draft_translation=draft_text,
        polished_translation=polished_text,
        notes=[]
    )


def apply_glossary(text: str, glossary_terms: List[GlossaryTerm]) -> str:
    """Replace glossary terms in text (simple string replacement)."""
    for term in sorted(glossary_terms, key=lambda t: len(t.zh), reverse=True):
        text = text.replace(term.zh, term.en)
    return text


def clean_draft_output(text: str) -> str:
    """Remove obvious prompt prefix shell from draft translation output.

    Some models may include prefix like 'Draft translation:' or explanatory
    text such as 'Here's the draft translation, keeping close...'.
    Remove common prefixes and any leading explanatory line.
    """
    text = text.strip()
    # Split into lines
    lines = text.splitlines()
    if lines:
        first_line = lines[0].strip()
        # Check if first line contains explanatory phrases at the start
        explanatory_phrases = [
            "here's the draft translation",
            "here is the draft translation",
            "here's the translation",
            "here is the translation",
        ]
        lower_first = first_line.lower()
        for phrase in explanatory_phrases:
            if lower_first.startswith(phrase):
                # If the line ends with a colon (likely a full explanatory line)
                # or contains a colon after the phrase, treat as explanatory line.
                # We'll remove the entire line if it seems to be purely explanatory.
                # Heuristic: if after removing the phrase, the remaining part
                # starts with a comma and contains more explanatory words,
                # remove the whole line.
                # For simplicity, if line ends with ':' remove whole line.
                if first_line.endswith(':'):
                    lines = lines[1:]
                else:
                    # Remove the phrase from the first line
                    remaining = first_line[len(phrase):].lstrip(": ,.-")
                    if remaining:
                        lines[0] = remaining
                    else:
                        lines = lines[1:]
                break
        # Reconstruct text from lines
        text = "\n".join(lines).strip()

    # Remove common prefixes (including those that may remain after line removal)
    prefixes = ["Draft translation:", "Translation:", "Draft:", "译文:", "翻译:",
                "Here's the draft translation:", "Here is the draft translation:",
                "Here's the translation:", "Here is the translation:",
                "Here's the draft translation,", "Here is the draft translation,"]
    for prefix in prefixes:
        if text.startswith(prefix):
            text = text[len(prefix):].strip()
            break
    return text


# Keys emitted by the Prompt B reviewer format. If any of these appear in a
# default polish output, the reviewer prompt leaked into the prose path and
# the scaffolding must be stripped before the result reaches the user.
_REVIEW_SCAFFOLD_KEYS = (
    "major_issue",
    "why_it_matters",
    "recommended_fix",
    "optional_notes",
)


def _strip_review_scaffolding(text: str) -> str:
    """Remove Prompt B reviewer scaffolding from a polished-output string.

    The default polish path must return reader-facing prose only. If the model
    (or a prior wiring bug) leaks the reviewer format, drop every line that
    begins with a reviewer key and everything that follows on that line's
    continuation block, up to the next blank line or another key.
    """
    import re

    # Pattern matches a line starting with a reviewer key followed by ':'
    # (allowing leading whitespace, optional markdown emphasis like **key:**).
    key_alt = "|".join(re.escape(k) for k in _REVIEW_SCAFFOLD_KEYS)
    # Split by a blank line so we can drop whole scaffolding blocks cleanly.
    blocks = re.split(r"\n\s*\n", text)
    key_line_re = re.compile(
        rf"^\s*[\*_`]*\s*({key_alt})\s*[\*_`]*\s*:", re.IGNORECASE
    )
    kept_blocks = []
    for block in blocks:
        lines = block.splitlines()
        # Drop lines that start a reviewer key, plus their continuation
        # lines (indented or immediately-following non-empty lines until the
        # next key or end of block).
        filtered: list[str] = []
        skip_continuation = False
        for line in lines:
            if key_line_re.match(line):
                skip_continuation = True
                continue
            if skip_continuation:
                # A continuation of the prior scaffold line: indented or a new
                # reviewer key. Keep skipping until a clearly unrelated line.
                if line.strip() == "":
                    skip_continuation = False
                    continue
                if key_line_re.match(line):
                    continue
                # Non-indented, non-key content: treat as prose resumption.
                if line.startswith((" ", "\t")):
                    continue
                skip_continuation = False
            filtered.append(line)
        remainder = "\n".join(filtered).strip()
        if remainder:
            kept_blocks.append(remainder)
    return "\n\n".join(kept_blocks).strip()


def clean_polished_output(text: str) -> str:
    """Normalize polished-translation output to reader-facing prose only.

    Removes:
      * common prefix shells like ``Polished translation:``
      * trailing explanatory sections (``Explanation:``, ``Note:`` etc.)
      * Prompt B reviewer scaffolding (``major_issue:`` etc.) if it leaks in

    The default workflow must return prose only; reviewer scaffolding is
    never exposed to the user.
    """
    text = text.strip()
    # Remove common prefixes
    prefixes = ["Polished translation:", "Polished:", "Refined translation:", "Translation:"]
    for prefix in prefixes:
        if text.startswith(prefix):
            text = text[len(prefix):].strip()
            break
    # Truncate at explanatory markers (case-insensitive)
    markers = ["\n\nExplanation:", "\n\nNote:", "\n\nNotes:", "\n\nAlternative:",
               "\n\nAlternatives:", "\n\nCommentary:", "\n\nComment:", "\n\n---"]
    for marker in markers:
        if marker in text:
            text = text.split(marker)[0].strip()
            break
    # Safety net: strip reviewer scaffolding if it leaked into the polish path.
    text = _strip_review_scaffolding(text)
    return text


def build_translation_input(segment: Segment, glossary_terms: Optional[List[GlossaryTerm]] = None) -> TranslationInput:
    """Convert a Segment to a TranslationInput."""
    if glossary_terms is None:
        glossary_terms = []
    return TranslationInput(
        segment_id=str(segment.segment_id),
        source_text=segment.text,
        prev_context=segment.prev_segment_text,
        next_context=segment.next_segment_text,
        glossary_terms=glossary_terms
    )


_ASSET_HEADINGS = {
    "characters": "Characters",
    "titles_and_terms": "Titles and terms",
    "glossary": "Glossary (project memory)",
    "style_notes": "Style notes",
    "unresolved_decisions": "Unresolved decisions",
}


def build_project_assets_block(assets_mode: AssetsMode = DEFAULT_ASSETS_MODE) -> str:
    """Build a single unified project-assets block for injection into model prompts.

    Reads the five governed assets via the read-only loader and renders them as
    a labeled block. Empty or missing assets are skipped. Returns an empty
    string if no assets are available.

    assets_mode:
      - "full" (default): inject all non-empty project assets
      - "none": skip asset injection entirely (returns "")
    """
    _validate_assets_mode(assets_mode)
    if assets_mode == "none":
        return ""
    assets = load_all_assets()
    sections = []
    for name in ASSET_NAMES:
        content = assets.get(name)
        if not content or not content.strip():
            continue
        heading = _ASSET_HEADINGS.get(name, name)
        sections.append(f"## {heading}\n{content.strip()}")
    if not sections:
        return ""
    body = "\n\n".join(sections)
    return (
        "Project memory (authoritative reference — follow these naming, "
        "glossary, and style decisions; do not override them):\n\n"
        f"{body}"
    )


def build_draft_prompt(
    input: TranslationInput,
    assets_mode: AssetsMode = DEFAULT_ASSETS_MODE,
) -> str:
    """Build a prompt for generating a faithful draft translation.

    Asks the model to translate Chinese text to English, preserving meaning,
    tone, and glossary terms. See ``build_project_assets_block`` for
    ``assets_mode`` semantics.
    """
    _validate_assets_mode(assets_mode)
    lines = []

    # Instruction block loaded from prompts/prompt_a.md
    lines.append(load_prompt("prompt_a").rstrip())
    lines.append("")

    # Project memory assets (characters, titles/terms, glossary, style, unresolved)
    assets_block = build_project_assets_block(assets_mode)
    if assets_block:
        lines.append(assets_block)
        lines.append("")

    # Glossary terms if present
    if input.glossary_terms:
        lines.append("Glossary terms (use these exact translations):")
        for term in input.glossary_terms:
            lines.append(f"  {term.zh} → {term.en}")
        lines.append("")

    # Previous context (optional) - as support only
    if input.prev_context:
        lines.append("Previous segment (for context only, do not translate):")
        lines.append(input.prev_context)
        lines.append("")

    # Next context (optional) - as support only
    if input.next_context:
        lines.append("Next segment (for context only, do not translate):")
        lines.append(input.next_context)
        lines.append("")

    # Original source text
    lines.append("Original Chinese text:")
    lines.append(input.source_text)
    lines.append("")

    lines.append("Draft translation:")

    return "\n".join(lines)


def build_polish_prompt(
    input: TranslationInput,
    draft_text: str,
    assets_mode: AssetsMode = DEFAULT_ASSETS_MODE,
    review_guidance: Optional["ReviewFindings"] = None,
) -> str:
    """Build a Prompt A-based revision prompt for a draft translation.

    This drives the Step 3 revision pass in the default workflow: the model
    takes the draft plus (optionally) a narrow review finding from Prompt B
    and returns corrected prose, not review notes.

    ``review_guidance`` — when present, the reviewer's ``major_issue`` and
    ``recommended_fix`` lines are injected as targeted instructions. The full
    reviewer scaffolding is never passed through; only the minimum signal the
    reviser needs.
    """
    _validate_assets_mode(assets_mode)
    lines = []

    # Prompt A is the project's prose/polish instruction set (WORKFLOW.md
    # §"Prompt A"). Revision is a prose-generation pass, not a review pass,
    # so it must run under Prompt A's rules.
    lines.append(load_prompt("prompt_a").rstrip())
    lines.append("")

    assets_block = build_project_assets_block(assets_mode)
    if assets_block:
        lines.append(assets_block)
        lines.append("")

    if input.glossary_terms:
        lines.append("Glossary terms (use these exact translations):")
        for term in input.glossary_terms:
            lines.append(f"  {term.zh} → {term.en}")
        lines.append("")

    if input.prev_context:
        lines.append("Previous segment (for context only, do not translate):")
        lines.append(input.prev_context)
        lines.append("")

    if input.next_context:
        lines.append("Next segment (for context only, do not translate):")
        lines.append(input.next_context)
        lines.append("")

    lines.append("Original Chinese text:")
    lines.append(input.source_text)
    lines.append("")

    lines.append("Draft translation to polish:")
    lines.append(draft_text)
    lines.append("")

    # Inject only the narrow signal from the reviewer, never the full
    # reviewer scaffolding. The output must be prose, not a review reply.
    if review_guidance is not None and review_guidance.has_major_issue():
        lines.append(
            "Reviewer guidance for this revision (apply narrowly, do not "
            "restructure the passage):"
        )
        if review_guidance.major_issue:
            lines.append(f"- Issue: {review_guidance.major_issue.strip()}")
        if review_guidance.recommended_fix:
            lines.append(f"- Fix: {review_guidance.recommended_fix.strip()}")
        lines.append("")
        lines.append(
            "Return only the revised English prose. Do not echo the reviewer "
            "fields (major_issue, why_it_matters, recommended_fix, "
            "optional_notes)."
        )
        lines.append("")

    lines.append("Polished translation:")

    return "\n".join(lines)


def build_review_prompt(
    input: TranslationInput,
    draft_text: str,
    assets_mode: AssetsMode = DEFAULT_ASSETS_MODE,
) -> str:
    """Build a Prompt B reviewer prompt over a draft translation.

    The output of running this prompt through the backend is reviewer
    scaffolding (``major_issue:`` / ``why_it_matters:`` / ``recommended_fix:``
    / ``optional_notes:``), not prose. It is used only for the internal
    Step 2 review pass and must never be surfaced to the user directly.
    """
    _validate_assets_mode(assets_mode)
    lines = [load_prompt("prompt_b").rstrip(), ""]

    assets_block = build_project_assets_block(assets_mode)
    if assets_block:
        lines.append(assets_block)
        lines.append("")

    if input.glossary_terms:
        lines.append("Glossary terms (use these exact translations):")
        for term in input.glossary_terms:
            lines.append(f"  {term.zh} → {term.en}")
        lines.append("")

    if input.prev_context:
        lines.append("Previous segment (for context only, do not translate):")
        lines.append(input.prev_context)
        lines.append("")

    if input.next_context:
        lines.append("Next segment (for context only, do not translate):")
        lines.append(input.next_context)
        lines.append("")

    lines.append("Original Chinese text:")
    lines.append(input.source_text)
    lines.append("")

    lines.append("English translation under review:")
    lines.append(draft_text)
    lines.append("")

    lines.append("Review:")
    return "\n".join(lines)


@dataclass
class ReviewFindings:
    """Parsed Prompt B reviewer output. Internal representation only."""

    raw: str
    major_issue: Optional[str] = None
    why_it_matters: Optional[str] = None
    recommended_fix: Optional[str] = None
    optional_notes: Optional[str] = None

    _NEGATIVE_PHRASES = (
        "none",
        "no major issue",
        "no issue",
        "no significant",
        "nothing",
        "n/a",
        "no problems",
        "no concerns",
    )

    def has_major_issue(self) -> bool:
        """True when the reviewer flagged a material problem worth revising for.

        Returns False if no ``major_issue`` field was parsed, if the field is
        empty, or if it contains a standard "no issue" phrasing.
        """
        if not self.major_issue:
            return False
        s = self.major_issue.strip().lower()
        if not s:
            return False
        return not any(neg in s for neg in self._NEGATIVE_PHRASES)


def check_segment_coverage(source_text: str, candidate_text: str) -> Optional[ReviewFindings]:
    """Deterministic coverage check for segment translations.

    Coarse-grained heuristic checks for potential omissions that the Prompt B
    review may have missed. Uses three rules:
      1. Paragraph count — source has >=4 paragraphs but candidate has <=1
      2. Dialogue count — source has >=4 dialogue utterances using Chinese
         opening quote marks such as U+300C LEFT CORNER BRACKET or U+201C
         LEFT DOUBLE QUOTATION MARK, but candidate has <30% as many
      3. Length ratio — source >=300 chars but candidate <20% of source length

    Returns a ReviewFindings with major_issue set if a likely omission is
    detected, or None if coverage looks adequate.
    """
    # ── Paragraph coverage ─────────────────────────────────────────────
    source_paras = [p for p in source_text.split('\n\n') if p.strip()]
    candidate_paras = [p for p in candidate_text.split('\n\n') if p.strip()]

    if len(source_paras) >= 4 and len(candidate_paras) <= 1:
        return ReviewFindings(
            raw="",
            major_issue=(
                f"Possible omission: source has {len(source_paras)} paragraphs "
                f"but output covers only {len(candidate_paras)} paragraph(s)"
            ),
            why_it_matters=(
                "Multiple distinct source paragraphs suggest significant "
                "content or structural breaks may be missing from the "
                "translation"
            ),
            recommended_fix=(
                f"Ensure all {len(source_paras)} source paragraphs are "
                "represented in the translation"
            ),
        )

    # ── Dialogue coverage ──────────────────────────────────────────────
    # Count Chinese left-corner bracket and Chinese double quotes as
    # dialogue utterances.  Source text may use 「」 or “” for dialogue.
    source_dialogues = source_text.count('「') + source_text.count('“')
    # Candidate (English) may use ASCII straight quotes or curly quotes.
    candidate_quotes = (candidate_text.count('"')
                        + candidate_text.count('“')
                        + candidate_text.count('”'))
    candidate_dialogues = candidate_quotes // 2

    if source_dialogues >= 4 and candidate_dialogues < max(1, source_dialogues * 0.3):
        return ReviewFindings(
            raw="",
            major_issue=(
                f"Possible omission: source has approximately "
                f"{source_dialogues} dialogue exchanges but output preserves "
                f"only about {candidate_dialogues}"
            ),
            why_it_matters=(
                "Missing dialogue lines lose character voice and scene pacing"
            ),
            recommended_fix=(
                "Ensure all dialogue exchanges from the source are "
                "represented in the translation"
            ),
        )

    # ── Length ratio ───────────────────────────────────────────────────
    if len(source_text) >= 300 and len(candidate_text) < len(source_text) * 0.2:
        return ReviewFindings(
            raw="",
            major_issue=(
                f"Output too short: source is {len(source_text)} characters "
                f"but output is only {len(candidate_text)} characters "
                f"({len(candidate_text) * 100 // len(source_text)}%)"
            ),
            why_it_matters=(
                "Extreme length disparity often indicates large portions of "
                "the source passage were not translated"
            ),
            recommended_fix=(
                "Expand the translation to proportionally cover the full "
                "source passage"
            ),
        )

    return None


def parse_review_findings(text: str) -> ReviewFindings:
    """Parse Prompt B reviewer output into a ``ReviewFindings`` record.

    Tolerates minor formatting variation: leading bullets, markdown emphasis
    (``**major_issue:**``), surrounding whitespace, and case. Fields that are
    not present stay as ``None``.
    """
    fields: dict[str, Optional[str]] = {k: None for k in _REVIEW_SCAFFOLD_KEYS}
    if not text:
        return ReviewFindings(raw=text or "")

    key_alt = "|".join(re.escape(k) for k in _REVIEW_SCAFFOLD_KEYS)
    # Find each key's position; slice between consecutive keys.
    pattern = re.compile(
        rf"(^|\n)\s*[\-\*]?\s*[\*_`]*\s*({key_alt})\s*[\*_`]*\s*:\s*",
        re.IGNORECASE,
    )
    matches = list(pattern.finditer(text))
    for i, m in enumerate(matches):
        key = m.group(2).lower()
        start = m.end()
        end = matches[i + 1].start() if i + 1 < len(matches) else len(text)
        value = text[start:end].strip()
        # Trim trailing markdown emphasis and stray punctuation.
        value = value.strip("*_` \n\t")
        fields[key] = value or None

    return ReviewFindings(
        raw=text,
        major_issue=fields["major_issue"],
        why_it_matters=fields["why_it_matters"],
        recommended_fix=fields["recommended_fix"],
        optional_notes=fields["optional_notes"],
    )


def _require_configured_backend(op_label: str):
    """Return (config, call_model_backend) or raise RuntimeError."""
    try:
        from app.config import config
        from app.translate.backend_adapter import call_model_backend
    except ImportError as e:
        raise RuntimeError(
            f"Backend {op_label} requested but required dependencies not "
            f"available: {e}. Install required dependencies "
            f"(e.g., 'pip install requests')."
        ) from e
    if not config.MODEL_BACKEND_URL or not config.MODEL_BACKEND_URL.strip():
        raise RuntimeError(
            f"MODEL_BACKEND_URL not configured. {op_label.capitalize()} "
            f"requires a real backend. Set MODEL_BACKEND_URL environment "
            f"variable to enable this step."
        )
    return config, call_model_backend


def run_internal_review_with_backend(
    input: TranslationInput,
    draft_text: str,
    assets_mode: AssetsMode = DEFAULT_ASSETS_MODE,
    budget_config: Optional[BudgetConfig] = None,
) -> str:
    """Call the backend with a Prompt B review prompt and return raw reviewer
    output.

    This is the Step 2 internal review pass. The return value contains
    reviewer scaffolding (``major_issue:`` etc.) and must be fed through
    ``parse_review_findings`` — never surfaced to the user directly.
    """
    _validate_assets_mode(assets_mode)
    _, call_model_backend = _require_configured_backend("internal review")
    prompt = build_review_prompt(input, draft_text, assets_mode)
    bc = budget_config or BudgetConfig()
    try:
        return call_model_backend(prompt, max_tokens=bc.review_max_tokens)
    except Exception as e:
        raise RuntimeError(f"Backend review call failed: {e}") from e


def translate_polish_with_backend(
    input: TranslationInput,
    draft_text: str,
    assets_mode: AssetsMode = DEFAULT_ASSETS_MODE,
    review_guidance: Optional[ReviewFindings] = None,
    budget_config: Optional[BudgetConfig] = None,
) -> str:
    """Call the backend with a Prompt A-based revision prompt and return
    cleaned prose.

    When ``review_guidance`` is provided and reports a major issue, only the
    ``major_issue`` / ``recommended_fix`` signal is injected into the prompt.
    Reviewer scaffolding is never passed through to the user.

    See ``build_project_assets_block`` for ``assets_mode`` semantics.

    Raises:
        RuntimeError: if MODEL_BACKEND_URL is not configured or backend call fails.
        ValueError: if assets_mode is not a recognized value.
    """
    _validate_assets_mode(assets_mode)
    _, call_model_backend = _require_configured_backend("polish")
    prompt = build_polish_prompt(
        input, draft_text, assets_mode, review_guidance=review_guidance
    )
    bc = budget_config or BudgetConfig()
    try:
        polished_text = call_model_backend(prompt, max_tokens=bc.polish_max_tokens)
    except Exception as e:
        raise RuntimeError(f"Backend polish call failed: {e}") from e

    return clean_polished_output(polished_text)


def mock_glossary() -> List[GlossaryTerm]:
    """Return a mock glossary for testing."""
    return [
        GlossaryTerm(zh="大小姐", en="Young Lady"),
        GlossaryTerm(zh="王爷", en="Prince"),
    ]
