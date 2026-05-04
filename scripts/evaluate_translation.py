#!/usr/bin/env python3
"""Evaluate a translated chapter against the Chinese source.

Calls DeepSeek API with a structured evaluation prompt.
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
  "summary": <2-3 sentence summary of main quality issues this round>
}}

Rules:
- bad_cases: only include issues that appear in THIS translation. Max 10.
- gold_cases: only genuinely excellent translations worth reusing. Max 5.
- proposed_asset_updates: only rules that would PREVENT RECURRING bad cases. Max 5.
- confidence > 0.8 = safe to auto-apply. confidence < 0.8 = needs human review.
- Return ONLY the JSON object. No prose, no markdown fences.
"""


def load_assets(assets_dir: Path) -> str:
    parts: list[str] = []
    for f in sorted(assets_dir.glob("*.md")):
        content = f.read_text(encoding="utf-8").strip()
        if content:
            parts.append(f"### {f.name}\n{content}")
    return "\n\n".join(parts) if parts else "(no assets loaded)"


def call_deepseek(system: str, user: str) -> str:
    # Load env from project .env.local if present
    env_local = PROJECT_ROOT / ".env.local"
    if env_local.exists():
        for line in env_local.read_text().splitlines():
            if "=" in line and not line.startswith("#"):
                k, _, v = line.partition("=")
                os.environ.setdefault(k.strip(), v.strip())

    api_key = os.environ.get("DEEPSEEK_API_KEY")
    base_url = os.environ.get("DEEPSEEK_BASE_URL", "https://api.deepseek.com/v1")
    if not api_key:
        sys.exit("evaluate_translation: DEEPSEEK_API_KEY not set")

    import requests as req
    resp = req.post(
        f"{base_url.rstrip('/')}/chat/completions",
        headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
        json={
            "model": "deepseek-chat",
            "max_tokens": 4096,
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
        },
        timeout=120,
    )
    resp.raise_for_status()
    return resp.json()["choices"][0]["message"]["content"] or ""


def main() -> int:
    ap = argparse.ArgumentParser(description="Evaluate a chapter translation.")
    ap.add_argument("--source", type=Path, required=True)
    ap.add_argument("--translation", type=Path, required=True)
    ap.add_argument("--assets-dir", type=Path,
                    default=PROJECT_ROOT / "project_assets")
    ap.add_argument("--output", type=Path, help="Save JSON report here")
    ap.add_argument("--dry-run", action="store_true",
                    help="Print prompt only, don't call API")
    args = ap.parse_args()

    if not args.source.exists():
        sys.exit(f"evaluate_translation: not found: {args.source}")

    if args.dry_run:
        print(f"[dry-run] source={args.source} translation={args.translation}")
        assets_block = load_assets(args.assets_dir)
        dummy_prompt = EVAL_PROMPT_TEMPLATE.format(
            assets_block=assets_block,
            source_text=args.source.read_text(encoding="utf-8").strip(),
            translation_text="(translation not yet generated — dry-run)",
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
    )

    print("evaluate_translation: calling DeepSeek...", file=sys.stderr)
    raw = call_deepseek(EVAL_SYSTEM, user_prompt)

    # Strip markdown fences if the model wrapped anyway
    raw = raw.strip()
    if raw.startswith("```"):
        raw = re.sub(r"^```[a-z]*\n?", "", raw)
        raw = re.sub(r"\n?```$", "", raw)

    try:
        import re
        report = json.loads(raw)
    except json.JSONDecodeError as e:
        sys.exit(f"evaluate_translation: could not parse JSON response: {e}\nRaw:\n{raw[:500]}")

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
