#!/usr/bin/env python3
"""Evaluate a translated chapter against the Chinese source.

Calls Claude via the `claude -p` CLI (Claude Code Pro auth — no API key needed).
Outputs a JSON report with bad_cases, gold_cases, proposed_asset_updates, score.

Usage:
  python scripts/evaluate_translation.py \
      --source data/source/one_chapter_quality_source.txt \
      --translation data/exports/one_chapter_quality_source_en.md \
      --assets-dir project_assets/ \
      --output data/quality_loop/round_001/eval.json
"""
from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).parent.parent

EVAL_SYSTEM = """\
You are a literary translation quality evaluator specializing in Chinese-to-English \
fiction translation. Your job is to identify translation failures and successes, \
then propose concrete improvements to the translation style guide.

You evaluate against the standard of 信达雅 (xin-da-ya):
  信 (xin): accuracy — faithful to the original meaning
  达 (da): fluency — natural, readable English prose
  雅 (ya): elegance — appropriate literary register for the genre

The target audience is an English-speaking young adult reader. The genre is \
Chinese historical/fantasy romance fiction. The style should be literary but \
accessible, not archaic.
"""

EVAL_PROMPT_TEMPLATE = """\
## Project Style Assets (current)
{assets_block}

## Chinese Source
{source_text}

## English Translation to Evaluate
{translation_text}

{human_review_block}

---

Evaluate this translation. Return ONLY valid JSON matching this exact schema:

{{
  "score": <float 0-10, overall quality>,
  "score_breakdown": {{
    "accuracy": <float 0-10>,
    "fluency": <float 0-10>,
    "elegance": <float 0-10>
  }},
  "bad_cases": [
    {{
      "type": <one of: "literal_translation"|"modern_slang"|"address_drift"|
               "tone_mismatch"|"narrative_misread"|"relationship_misread"|
               "chinese_residual"|"paragraph_repeat"|"truncation"|"other">,
      "chinese_original": <exact Chinese sentence/phrase>,
      "bad_translation": <the problematic English>,
      "explanation": <why this is wrong>,
      "suggested_fix": <better English>,
      "severity": <"critical"|"major"|"minor">
    }}
  ],
  "gold_cases": [
    {{
      "chinese_original": <exact Chinese>,
      "excellent_translation": <the English>,
      "why_good": <what makes this translation excellent>
    }}
  ],
  "proposed_asset_updates": [
    {{
      "target_file": <"glossary.md"|"style_notes.md"|"characters.md"|
                     "titles_and_terms.md"|"gold_examples.md">,
      "action": <"add"|"modify"|"remove">,
      "content": <exact text to add/modify>,
      "reason": <why this update would help future translations>,
      "confidence": <float 0-1>
    }}
  ],
  "human_review_checklist": [
    {{
      "signal": <human-review bullet/signal being checked>,
      "judgment": <"caught"|"missed"|"unclear">,
      "evidence": <brief source/translation/evaluator evidence>,
      "linked_case": <bad_cases/gold_cases index or null>
    }}
  ],
  "summary": <2-3 sentence summary of main quality issues this round>
}}

Rules:
- bad_cases: only include issues that appear in THIS translation. Max 10.
- gold_cases: only genuinely excellent translations worth reusing. Max 5.
- proposed_asset_updates: only rules that would PREVENT RECURRING bad cases. Max 5.
- confidence > 0.8 = safe to auto-apply. confidence < 0.8 = needs human review.
- When human review signals are provided, prioritize diverging human-review
  signals in bad_cases before ordinary non-calibration issues. Do not praise a
  rendering in gold_cases if it diverges from the expected human correction.
  If human review calibration conflicts with project assets, treat the human
  review signal as validation ground truth for checklist and case judgments.
  Never list the same Chinese span or English rendering in both bad_cases and
  gold_cases; before finalizing, audit every gold_cases item against bad_cases.
  If a gold candidate has the same chinese_original, same English rendering, or
  a containing source span as a bad_case, remove it from gold_cases or narrow it
  to only the independently correct sub-span. Do not keep a gold case with a
  caveat that part of the same source span is wrong. If any part of a rendering
  is called wrong, it is not reusable gold for this report.
  Exact or acceptable matches to human-review signals
  should be marked caught in human_review_checklist with linked_case null
  unless they are independently excellent, reusable examples. Do not turn
  harmless formatting differences, capitalization, comma placement, or wording
  that preserves the expected meaning/register into bad_cases. A correct term
  without an explanatory gloss, or a correct kinship/legal relation followed by
  an appositive name, is an acceptable match: mark caught with linked_case null,
  not a bad_case. For rare body/diagnostic technical terms such as 泪堂, a
  rendering like "Tear Hall beneath her eyes" is an acceptable term-with-location
  match for "Tear Hall, the area beneath the eyes"; mark caught with linked_case
  null and do not create a bad_case.
- Severity calibration: critical = truncation, repetition/merge artifact, or
  meaning failure that breaks the passage; major = human-review divergence that
  changes title meaning, relationship/address, terminology, dialogue force, or
  narrative stance; minor = local polish issue with meaning intact. If bad_cases
  is near the limit, keep critical/major human-review divergences and drop minor
  polish complaints first.
- human_review_checklist: if human review signals are provided, include one item
  for every bullet/signal from that section. This checklist measures whether
  this evaluator caught the human-review signal, not whether the translation
  was correct. Decide caught/missed/unclear first by comparing the signal
  against the source and translation; choose linked_case only after judgment.
  Lack of a linked_case must never prevent "caught". Mark "caught" when an
  incorrect rendering is explicitly reported in bad_cases, when a correct/strong
  rendering is explicitly reported in gold_cases, or when the translation is an
  exact/acceptable match that needs no bad_case or gold_case. Exact/acceptable
  matches use linked_case null; do not use "missed" or "unclear" merely because
  a match has no linked case or is not reusable gold. Mark "missed" only when
  the source/translation contains the signal but the evaluator failed to account
  for it at all. linked_case may point to bad_cases only when the checklist
  signal is an actual failure reported in bad_cases; it may point to gold_cases
  only when the signal is a reusable gold example. If judgment is "caught"
  because the rendering is acceptable, linked_case must be null and the item
  must not be listed in bad_cases. A "missed" checklist item must never
  coexist with a gold_cases item praising the same disputed source span. Mark
  "unclear" only when the signal cannot be located or compared.
  If no human review is provided, return an empty array.
- Return ONLY the JSON object. No prose, no markdown fences.
"""


def load_assets(assets_dir: Path) -> str:
    parts: list[str] = []
    for f in sorted(assets_dir.glob("*.md")):
        content = f.read_text(encoding="utf-8").strip()
        if content:
            parts.append(f"### {f.name}\n{content}")
    return "\n\n".join(parts) if parts else "(no assets loaded)"


def load_human_review(path: Path | None) -> str:
    if path is None:
        return ""
    if not path.exists():
        sys.exit(f"evaluate_translation: human review not found: {path}")
    content = path.read_text(encoding="utf-8").strip()
    if not content:
        sys.exit(f"evaluate_translation: human review is empty: {path}")
    return content


def build_human_review_block(content: str) -> str:
    if not content:
        return ""
    return (
        "## Human Review Calibration Signals (must-check)\n"
        "The following human-reviewed notes are explicit calibration signals. "
        "Treat each bullet or line-level correction as its own signal. For "
        "every signal, compare the Chinese source, English translation, and "
        "the expected human correction. If the translation diverges, report "
        "the issue in bad_cases, even for phrase-level terminology, title, "
        "dialogue, kinship-address, and narrative-stance signals that might "
        "otherwise seem too small. Prioritize these human-review divergences "
        "in bad_cases before ordinary non-calibration issues. If human review "
        "calibration conflicts with project assets, treat the human review "
        "signal as validation ground truth for checklist and case judgments. "
        "If the translation "
        "differs from the expected correction, do not praise that rendering in "
        "gold_cases merely because it is fluent or close in spirit; any span "
        "listed in bad_cases is ineligible for gold_cases. If it matches well, "
        "mark the signal caught in the checklist with linked_case null; report "
        "it in gold_cases only when it is independently one of the strongest "
        "reusable examples. Do not over-flag exact or acceptable matches for "
        "minor punctuation, capitalization, comma placement, or wording changes "
        "that preserve the expected meaning and register. A correct term without "
        "an explanatory gloss, or a correct kinship/legal relation followed by "
        "an appositive name, is an acceptable match: mark caught with linked_case "
        "null, not a bad_case. For rare body/diagnostic technical terms such as "
        "泪堂, a rendering like \"Tear Hall beneath her eyes\" is an acceptable "
        "term-with-location match for \"Tear Hall, the area beneath the eyes\"; "
        "mark caught with linked_case null and do not create a bad_case. "
        "Calibrate severity: "
        "critical for truncation, repetition/merge artifacts, or meaning failure "
        "that breaks the passage; major for human-review divergences that change "
        "title meaning, relationship/address, terminology, dialogue force, or "
        "narrative stance; minor only for local polish issues with meaning "
        "intact. If bad_cases is near the limit, keep critical/major "
        "human-review divergences and drop minor polish complaints first. "
        "You must also complete "
        "human_review_checklist with one caught/missed/unclear judgment per "
        "signal and brief evidence; do not silently skip any signal. In the "
        "checklist, caught/missed/unclear describes evaluator coverage, not "
        "translation correctness. Decide caught/missed/unclear first by "
        "comparing the signal against the source and translation; choose "
        "linked_case only after judgment. Lack of a linked_case must never "
        "prevent caught. A wrong translation is caught when you list it in "
        "bad_cases; a good reusable translation is caught when you list it in "
        "gold_cases; an exact or acceptable match is also caught with "
        "linked_case null when it needs no bad_case or gold_case. Do not mark "
        "a match missed or unclear merely because it has no linked case or is "
        "not reusable gold. Missed means the signal appears in the "
        "source/translation but was not accounted for at all. linked_case may "
        "point to bad_cases only for actual failures reported in bad_cases, "
        "and to gold_cases only for reusable gold examples. If judgment is "
        "caught because the rendering is acceptable, linked_case must be null "
        "and the item must not be listed in bad_cases. A missed checklist item "
        "must never coexist with a gold_cases item praising the same disputed "
        "source span.\n\n"
        f"{content}"
    )


# JSON Schema mirrors the prompt template above. Constrains the CLI response
# to a parseable, length-bounded shape — without this, long explanations
# truncated at the default text-output budget produced unparseable JSON
# (failure mode observed on round_011/ch010, 2026-05-06).
EVAL_SCHEMA = {
    "type": "object",
    "properties": {
        "score": {"type": "number", "minimum": 0, "maximum": 10},
        "score_breakdown": {
            "type": "object",
            "properties": {
                "accuracy": {"type": "number", "minimum": 0, "maximum": 10},
                "fluency": {"type": "number", "minimum": 0, "maximum": 10},
                "elegance": {"type": "number", "minimum": 0, "maximum": 10},
            },
            "required": ["accuracy", "fluency", "elegance"],
        },
        "bad_cases": {
            "type": "array",
            "maxItems": 10,
            "items": {
                "type": "object",
                "properties": {
                    "type": {"type": "string"},
                    "chinese_original": {"type": "string"},
                    "bad_translation": {"type": "string"},
                    "explanation": {"type": "string", "maxLength": 600},
                    "suggested_fix": {"type": "string", "maxLength": 600},
                    "severity": {"type": "string"},
                },
                "required": ["type", "chinese_original", "bad_translation", "explanation"],
            },
        },
        "gold_cases": {
            "type": "array",
            "maxItems": 5,
            "items": {
                "type": "object",
                "properties": {
                    "chinese_original": {"type": "string"},
                    "excellent_translation": {"type": "string"},
                    "why_good": {"type": "string", "maxLength": 400},
                },
                "required": ["chinese_original", "excellent_translation", "why_good"],
            },
        },
        "proposed_asset_updates": {
            "type": "array",
            "maxItems": 5,
            "items": {
                "type": "object",
                "properties": {
                    "target_file": {"type": "string"},
                    "action": {"type": "string"},
                    "content": {"type": "string"},
                    "reason": {"type": "string", "maxLength": 400},
                    "confidence": {"type": "number", "minimum": 0, "maximum": 1},
                },
                "required": ["target_file", "action", "content", "confidence"],
            },
        },
        "human_review_checklist": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "signal": {"type": "string", "maxLength": 400},
                    "judgment": {
                        "type": "string",
                        "enum": ["caught", "missed", "unclear"],
                    },
                    "evidence": {"type": "string", "maxLength": 500},
                    "linked_case": {
                        "anyOf": [
                            {"type": "integer"},
                            {"type": "string", "maxLength": 80},
                            {"type": "null"},
                        ]
                    },
                },
                "required": ["signal", "judgment", "evidence", "linked_case"],
            },
        },
        "summary": {"type": "string", "maxLength": 800},
    },
    "required": [
        "score",
        "bad_cases",
        "gold_cases",
        "proposed_asset_updates",
        "human_review_checklist",
    ],
}


def parse_linked_case_ref(linked_case) -> tuple[str | None, int | None]:
    """Return (case_collection, index) for linked_case values."""
    if isinstance(linked_case, int):
        return None, linked_case
    if isinstance(linked_case, str):
        match = re.fullmatch(r"\s*(bad_cases|gold_cases)\[(\d+)\]\s*", linked_case)
        if match:
            return match.group(1), int(match.group(2))
    return None, None


def source_span_overlaps_signal(source_span: str, signal: str) -> bool:
    """Return whether a case source span and checklist signal refer to the same text."""
    if not source_span:
        return False
    source_span = str(source_span)
    signal = str(signal)
    signal_source = re.split(r"\s*(?:->|→)\s*", signal, maxsplit=1)[0].strip()
    return (
        source_span in signal
        or source_span in signal_source
        or signal_source in source_span
    )


def matching_case_refs_for_signal(report: dict, signal: str) -> list[str]:
    """Return exact bad/gold case refs whose Chinese source appears in signal."""
    matches: list[str] = []
    for collection in ("bad_cases", "gold_cases"):
        for index in matching_case_indices(report, collection, signal):
            matches.append(f"{collection}[{index}]")
    return matches


def matching_case_indices(report: dict, collection: str, signal: str) -> list[int]:
    """Return case indexes in one collection whose Chinese source appears in signal."""
    matches: list[int] = []
    for index, case in enumerate(report.get(collection) or []):
        source = case.get("chinese_original")
        if source and str(source) in signal:
            matches.append(index)
    return matches


def link_caught_checklist_items(report: dict) -> None:
    """Fill unambiguous linked_case refs for caught human-review checklist items."""
    for item in report.get("human_review_checklist") or []:
        if item.get("judgment") != "caught" or item.get("linked_case") is not None:
            continue
        matches = matching_case_refs_for_signal(report, str(item.get("signal") or ""))
        if len(matches) == 1:
            item["linked_case"] = matches[0]


def validate_report_contract(report: dict) -> None:
    """Validate deterministic evaluator JSON contracts.

    This is intentionally small and backend-agnostic: it checks only report
    shape/linking invariants that can be verified without re-running a model.
    """
    bad_cases = report.get("bad_cases") or []
    gold_cases = report.get("gold_cases") or []

    duplicate_sources = []
    for bad_index, bad_case in enumerate(bad_cases):
        bad_source = bad_case.get("chinese_original")
        if not bad_source:
            continue
        for gold_index, gold_case in enumerate(gold_cases):
            if bad_source == gold_case.get("chinese_original"):
                duplicate_sources.append(
                    f"bad_cases[{bad_index}].chinese_original == "
                    f"gold_cases[{gold_index}].chinese_original: "
                    f"{bad_source!r}"
                )
    if duplicate_sources:
        raise ValueError(
            "evaluator report lists the same chinese_original in "
            "bad_cases and gold_cases: "
            + "; ".join(duplicate_sources)
        )

    for index, case in enumerate(bad_cases):
        missing = [
            key
            for key in ("type", "chinese_original", "bad_translation", "explanation")
            if not case.get(key)
        ]
        if missing:
            raise ValueError(
                f"bad_cases[{index}] missing bad-case schema fields: {missing!r}"
            )

    for index, case in enumerate(gold_cases):
        missing = [
            key
            for key in ("excellent_translation", "why_good")
            if not case.get(key)
        ]
        if missing:
            raise ValueError(
                f"gold_cases[{index}] missing gold schema fields: {missing!r}"
            )

    checklist_schema = EVAL_SCHEMA["properties"]["human_review_checklist"]["items"]
    checklist_required = checklist_schema["required"]
    allowed_judgments = set(
        checklist_schema["properties"]["judgment"]["enum"]
    )

    for index, item in enumerate(report.get("human_review_checklist") or []):
        missing = [
            key
            for key in checklist_required
            if key not in item or (key != "linked_case" and not item.get(key))
        ]
        if missing:
            raise ValueError(
                f"human_review_checklist[{index}] missing checklist "
                f"schema fields: {missing!r}"
            )

        if item["judgment"] not in allowed_judgments:
            raise ValueError(
                f"human_review_checklist[{index}] invalid judgment: "
                f"{item['judgment']!r}"
            )

        linked_case = item["linked_case"]
        linked_collection, linked_index = parse_linked_case_ref(linked_case)
        if linked_case is not None and linked_index is None:
            raise ValueError(
                f"human_review_checklist[{index}] invalid linked_case "
                f"reference: {linked_case!r}"
            )
        if linked_index is not None and (
            linked_index < 0
            or (
                linked_collection == "bad_cases"
                and linked_index >= len(bad_cases)
            )
            or (
                linked_collection == "gold_cases"
                and linked_index >= len(gold_cases)
            )
            or (
                linked_collection is None
                and linked_index >= len(bad_cases)
                and linked_index >= len(gold_cases)
            )
        ):
            raise ValueError(
                f"human_review_checklist[{index}] linked_case out of range: "
                f"{linked_case!r}"
            )

        if item["judgment"] == "missed":
            matching_gold = [
                i
                for i, case in enumerate(gold_cases)
                if source_span_overlaps_signal(
                    str(case.get("chinese_original") or ""),
                    str(item["signal"]),
                )
            ]
            if matching_gold:
                raise ValueError(
                    "missed checklist item cannot coexist with matching "
                    "gold_cases item: "
                    f"human_review_checklist[{index}] matches "
                    + ", ".join(f"gold_cases[{i}]" for i in matching_gold)
                )

        if item["judgment"] != "caught":
            continue

        signal = str(item["signal"])
        matching_bad = matching_case_indices(report, "bad_cases", signal)
        matching_gold = matching_case_indices(report, "gold_cases", signal)

        if linked_case is None:
            if matching_bad or matching_gold:
                raise ValueError(
                    "caught checklist item with matching case must link to "
                    f"that case: human_review_checklist[{index}]"
                )
            continue

        valid_bad_link = (
            linked_index is not None
            and linked_collection in (None, "bad_cases")
            and linked_index in matching_bad
        )
        valid_gold_link = (
            linked_index is not None
            and linked_collection in (None, "gold_cases")
            and linked_index in matching_gold
        )
        if not (valid_bad_link or valid_gold_link):
            raise ValueError(
                "caught checklist item linked_case does not point to a "
                f"matching bad_cases/gold_cases item: "
                f"human_review_checklist[{index}]"
            )


def raw_response_debug_path(output_path: Path) -> Path:
    return output_path.with_suffix(".raw_response.txt")


def write_raw_response_debug(raw: str, output_path: Path) -> Path:
    debug_path = raw_response_debug_path(output_path)
    debug_path.parent.mkdir(parents=True, exist_ok=True)
    debug_path.write_text(raw, encoding="utf-8")
    return debug_path


def contract_rejected_debug_path(output_path: Path) -> Path:
    return output_path.with_suffix(".contract_rejected.json")


def write_contract_rejected_debug(report: dict, output_path: Path) -> Path:
    debug_path = contract_rejected_debug_path(output_path)
    debug_path.parent.mkdir(parents=True, exist_ok=True)
    debug_path.write_text(
        json.dumps(report, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    return debug_path


# Confirmed Claude rate/quota/time-window limit signals (case-insensitive).
# Matched against api_error_status, the result text in the envelope, and
# stderr. Anything that does NOT match here is treated as an unrelated
# failure and re-raised — the auto fallback never silently masks parse,
# schema, network, or unknown errors.
_CLAUDE_RATE_LIMIT_RE = re.compile(
    r"(rate.?limit|usage.?limit|quota|429|5.?hour.?limit|daily.?limit|"
    r"too.?many.?requests|message.?limit|reset.?at)",
    re.IGNORECASE,
)


class ClaudeRateLimitError(RuntimeError):
    """Raised when Claude returns a confirmed rate/quota/time-window limit.

    Distinct from generic RuntimeError so the auto-fallback dispatcher can
    catch this specifically and switch to DeepSeek without masking other
    failures.
    """


def _is_claude_rate_limit(envelope: dict | None, stderr: str, returncode: int) -> bool:
    if envelope is not None and envelope.get("is_error"):
        status_str = str(envelope.get("api_error_status") or "")
        result_str = str(envelope.get("result") or "")
        if "429" in status_str or _CLAUDE_RATE_LIMIT_RE.search(status_str):
            return True
        if _CLAUDE_RATE_LIMIT_RE.search(result_str):
            return True
    if returncode != 0 and _CLAUDE_RATE_LIMIT_RE.search(stderr or ""):
        return True
    return False


def call_claude(system: str, user: str, model: str = "claude-opus-4-7") -> str:
    # --json-schema requires --output-format json; structured response lives
    # under .structured_output inside the result envelope. Without
    # --output-format json the schema validates internally but stdout is
    # empty in text mode (observed on round_011/ch010, 2026-05-06).
    result = subprocess.run(
        [
            "claude", "-p",
            "--model", model,
            "--system-prompt", system,
            "--json-schema", json.dumps(EVAL_SCHEMA),
            "--output-format", "json",
            "--tools", "",
            "--no-session-persistence",
        ],
        input=user,
        capture_output=True,
        text=True,
        timeout=300,
    )

    # Try to parse the envelope first — needed for both error and success
    # paths (rate-limit signals can live in api_error_status / result).
    envelope: dict | None = None
    try:
        envelope = json.loads(result.stdout.strip()) if result.stdout.strip() else None
    except (json.JSONDecodeError, ValueError):
        envelope = None

    if result.returncode != 0 or (envelope and envelope.get("is_error")):
        if _is_claude_rate_limit(envelope, result.stderr, result.returncode):
            detail = (
                str((envelope or {}).get("api_error_status") or "")
                or str((envelope or {}).get("result") or "")
                or (result.stderr or "").strip()[:200]
            )
            raise ClaudeRateLimitError(f"Claude rate-limited: {detail[:300]}")
        # Any other failure — surface loudly, do NOT auto-fall-back.
        raise RuntimeError(
            f"claude CLI failed (exit {result.returncode}): "
            f"{(result.stderr or '').strip()[:300]}"
        )

    if envelope is None:
        raise RuntimeError("claude returned empty stdout despite exit 0")
    structured = envelope.get("structured_output")
    if structured is None:
        raise RuntimeError(
            f"claude returned no structured_output. envelope keys: {list(envelope)}"
        )
    return json.dumps(structured, ensure_ascii=False)


def call_deepseek(system: str, user: str) -> str:
    """Call DeepSeek's chat-completions API.

    No --json-schema equivalent exists, so the prompt-shaped JSON instruction
    in EVAL_PROMPT_TEMPLATE is the only structure guarantee. Used directly
    when --evaluator deepseek, or as the auto-fallback target when Claude
    is rate-limited.
    """
    # Lazy-load .env.local so this script works standalone without the
    # caller having sourced the env file first.
    env_local = PROJECT_ROOT / ".env.local"
    if env_local.exists():
        for line in env_local.read_text().splitlines():
            if "=" in line and not line.startswith("#"):
                k, _, v = line.partition("=")
                os.environ[k.strip()] = v.strip()  # .env.local wins over shell env

    api_key = os.environ.get("DEEPSEEK_API_KEY")
    base_url = os.environ.get("DEEPSEEK_BASE_URL", "https://api.deepseek.com/v1")
    if not api_key:
        raise RuntimeError(
            "evaluate_translation: DEEPSEEK_API_KEY not set "
            "(required for --evaluator deepseek or auto-fallback)"
        )

    import requests as req
    resp = req.post(
        f"{base_url.rstrip('/')}/chat/completions",
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        },
        json={
            "model": "deepseek-chat",
            "max_tokens": 8192,
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
        },
        timeout=180,
    )
    if resp.status_code != 200:
        raise RuntimeError(
            f"deepseek API {resp.status_code}: {resp.text[:300]}"
        )
    return resp.json()["choices"][0]["message"]["content"]


def evaluate(system: str, user: str, mode: str) -> tuple[str, str]:
    """Dispatch to the chosen evaluator. Returns (raw_response, backend_tag)."""
    if mode == "claude":
        return call_claude(system, user), "claude"
    if mode == "deepseek":
        return call_deepseek(system, user), "deepseek-explicit"
    if mode == "auto":
        try:
            return call_claude(system, user), "claude"
        except ClaudeRateLimitError as e:
            print(
                f"evaluate_translation: Claude rate-limited, "
                f"falling back to DeepSeek ({e})",
                file=sys.stderr,
            )
            return call_deepseek(system, user), "deepseek-fallback"
    raise ValueError(f"unknown evaluator mode: {mode!r}")


def main() -> int:
    ap = argparse.ArgumentParser(description="Evaluate a chapter translation.")
    ap.add_argument("--source", type=Path, required=True)
    ap.add_argument("--translation", type=Path, required=True)
    ap.add_argument("--assets-dir", type=Path,
                    default=PROJECT_ROOT / "project_assets")
    ap.add_argument("--output", type=Path, help="Save JSON report here")
    ap.add_argument("--evaluator", choices=["claude", "deepseek", "auto"],
                    default="auto",
                    help="Evaluator backend. 'auto' (default): try Claude, "
                         "fall back to DeepSeek on confirmed rate-limit. "
                         "'claude': Claude only, fail on rate-limit. "
                         "'deepseek': DeepSeek only, no Claude call.")
    ap.add_argument("--human-review", type=Path,
                    help="Optional markdown file with human-reviewed "
                         "must-check calibration signals.")
    ap.add_argument("--dry-run", action="store_true",
                    help="Print prompt only, don't call API")
    args = ap.parse_args()

    if not args.source.exists():
        sys.exit(f"evaluate_translation: not found: {args.source}")
    human_review = load_human_review(args.human_review)
    human_review_block = build_human_review_block(human_review)

    if args.dry_run:
        print(f"[dry-run] source={args.source} translation={args.translation}")
        if args.human_review:
            print(f"[dry-run] human_review={args.human_review}")
        assets_block = load_assets(args.assets_dir)
        dummy_prompt = EVAL_PROMPT_TEMPLATE.format(
            assets_block=assets_block,
            source_text=args.source.read_text(encoding="utf-8").strip(),
            translation_text="(translation not yet generated — dry-run)",
            human_review_block=human_review_block,
        )
        print(f"[dry-run] ~{len(dummy_prompt) // 4} input tokens estimated")
        return 0

    if not args.translation.exists():
        sys.exit(f"evaluate_translation: not found: {args.translation}")

    source_text = args.source.read_text(encoding="utf-8").strip()
    translation_text = args.translation.read_text(encoding="utf-8").strip()
    assets_block = load_assets(args.assets_dir)

    user_prompt = EVAL_PROMPT_TEMPLATE.format(
        assets_block=assets_block,
        source_text=source_text,
        translation_text=translation_text,
        human_review_block=human_review_block,
    )

    print(f"evaluate_translation: evaluator={args.evaluator}", file=sys.stderr)
    raw, backend = evaluate(EVAL_SYSTEM, user_prompt, args.evaluator)

    # Strip markdown fences if the model wrapped anyway (DeepSeek path
    # sometimes emits fenced JSON despite the prompt's "no markdown" rule)
    raw = raw.strip()
    if raw.startswith("```"):
        raw = re.sub(r"^```[a-z]*\n?", "", raw)
        raw = re.sub(r"\n?```$", "", raw)

    try:
        report = json.loads(raw)
    except json.JSONDecodeError as e:
        debug_note = ""
        if args.output:
            debug_path = write_raw_response_debug(raw, args.output)
            debug_note = f"\nRaw response saved to: {debug_path}"
        sys.exit(
            f"evaluate_translation: could not parse JSON response: {e}"
            f"{debug_note}\nRaw:\n{raw[:500]}"
        )

    # Tag the report with which backend produced it so downstream consumers
    # (quality_loop state.json, staging.md header) can record provenance.
    report["backend"] = backend
    link_caught_checklist_items(report)
    try:
        validate_report_contract(report)
    except ValueError as e:
        debug_note = ""
        if args.output:
            debug_path = write_contract_rejected_debug(report, args.output)
            debug_note = f"\nContract-rejected report saved to: {debug_path}"
        sys.exit(
            f"evaluate_translation: invalid report contract: {e}"
            f"{debug_note}"
        )

    print(f"evaluate_translation: backend={backend}", file=sys.stderr)

    output_str = json.dumps(report, ensure_ascii=False, indent=2)

    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(output_str, encoding="utf-8")
        print(f"evaluate_translation: report → {args.output}", file=sys.stderr)
    else:
        print(output_str)

    # Print summary to stderr for loop visibility
    score = report.get("score", "?")
    n_bad = len(report.get("bad_cases", []))
    n_gold = len(report.get("gold_cases", []))
    n_updates = len(report.get("proposed_asset_updates", []))
    print(
        f"evaluate_translation: score={score}/10 "
        f"bad={n_bad} gold={n_gold} proposed_updates={n_updates}",
        file=sys.stderr,
    )
    print(f"  summary: {report.get('summary', '')}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
