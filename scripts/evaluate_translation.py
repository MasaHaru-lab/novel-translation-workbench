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
- human_review_checklist: if human review signals are provided, include one item
  for every bullet/signal from that section. Mark "caught" only when the signal
  is explicitly handled in bad_cases or gold_cases. Mark "missed" when the
  source/translation contains the signal but the main evaluation did not handle
  it. Mark "unclear" only when the signal cannot be located or compared.
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
        "the issue in bad_cases. If it matches well, report it in gold_cases "
        "when it is one of the strongest examples. You must also complete "
        "human_review_checklist with one caught/missed/unclear judgment per "
        "signal and brief evidence; do not silently skip any signal.\n\n"
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
        sys.exit(f"evaluate_translation: could not parse JSON response: {e}\nRaw:\n{raw[:500]}")

    # Tag the report with which backend produced it so downstream consumers
    # (quality_loop state.json, staging.md header) can record provenance.
    report["backend"] = backend

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
