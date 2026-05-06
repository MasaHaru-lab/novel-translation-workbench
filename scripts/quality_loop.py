#!/usr/bin/env python3
"""Quality iteration loop for novel-translation-workbench.

Runs N rounds of: translate → evaluate → stage proposed asset updates for review.
Nothing is written to project_assets/ automatically. All proposals land in
round_XXX/staging.md for Claude in-session review before any asset is touched.

Usage:
  python scripts/quality_loop.py --rounds 3              # new batch, round counter continues
  python scripts/quality_loop.py --rounds 3 --continue   # resume current batch (same batch number)
  python scripts/quality_loop.py --rounds 3 --reset      # destructive: wipe state.json, start over
  python scripts/quality_loop.py --rounds 3 --dry-run    # verify pipeline, no API calls

State is preserved across invocations. A default run (no flag) bumps the batch
number but keeps the monotonic round counter and the rounds[] history. Use
--reset only when you genuinely want to throw away all prior history.
"""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import textwrap
from datetime import datetime, timezone
from pathlib import Path

PROJECT_ROOT = Path(__file__).parent.parent
LOOP_DIR = PROJECT_ROOT / "data" / "quality_loop"
ASSETS_DIR = PROJECT_ROOT / "project_assets"
STATE_FILE = LOOP_DIR / "state.json"

DEFAULT_SOURCE = PROJECT_ROOT / "data" / "source" / "one_chapter_quality_source.txt"
DEFAULT_PROFILE = "deepseek-v4-flash"
DEFAULT_BOOK_MEMORY = PROJECT_ROOT / "data" / "book_memory" / "book_memory.json"

# Asset filename map — DeepSeek uses bare names; actual files dropped the numeric prefix
ASSET_FILE_MAP = {
    "glossary.md": "glossary.md",
    "characters.md": "characters.md",
    "titles_and_terms.md": "titles_and_terms.md",
    "style_notes.md": "style_notes.md",
    "unresolved_decisions.md": "unresolved_decisions.md",
    "gold_examples.md": "gold_examples.md",
}


# ── State management ──────────────────────────────────────────────────────────

def load_state() -> dict:
    if STATE_FILE.exists():
        return json.loads(STATE_FILE.read_text())
    return {
        "batch": 0,
        "total_rounds": 0,
        "rounds": [],
        "started_at": datetime.now(timezone.utc).isoformat(),
    }


def save_state(state: dict) -> None:
    LOOP_DIR.mkdir(parents=True, exist_ok=True)
    STATE_FILE.write_text(json.dumps(state, ensure_ascii=False, indent=2))


# ── Helpers ───────────────────────────────────────────────────────────────────

def run(cmd: list[str], label: str, dry_run: bool = False) -> subprocess.CompletedProcess:
    print(f"\n[{label}] $ {' '.join(str(c) for c in cmd)}", flush=True)
    if dry_run:
        print(f"[{label}] (dry-run — skipped)")
        return subprocess.CompletedProcess(cmd, 0, "", "")
    result = subprocess.run(cmd, capture_output=False)
    if result.returncode != 0:
        print(f"[{label}] FAILED (exit {result.returncode})")
    return result


def round_dir(round_num: int) -> Path:
    return LOOP_DIR / f"round_{round_num:03d}"


def write_staging_file(rdir: Path, eval_report: dict, round_num: int) -> Path:
    """Write all proposed updates to a staging file. Nothing touches project_assets/."""
    updates = eval_report.get("proposed_asset_updates", [])
    bad_cases = eval_report.get("bad_cases", [])
    gold_cases = eval_report.get("gold_cases", [])
    staging_path = rdir / "staging.md"

    lines = [
        f"# Round {round_num:03d} — Staging for Review",
        f"Generated: {datetime.now(timezone.utc).isoformat()}",
        f"Backend: {eval_report.get('backend', 'unknown')}",
        f"Score: {eval_report.get('score', '?')}/10",
        "",
        f"> {eval_report.get('summary', '')}",
        "",
    ]

    if bad_cases:
        lines += [f"## Bad Cases ({len(bad_cases)})", ""]
        for i, bc in enumerate(bad_cases, 1):
            sev = bc.get("severity", "?").upper()
            lines += [
                f"### {i}. [{sev}] {bc.get('type', '?')}",
                f"- **ZH:** {bc.get('chinese_original', '')}",
                f"- **Bad:** {bc.get('bad_translation', '')}",
                f"- **Fix:** {bc.get('suggested_fix', '')}",
                f"- **Why:** {bc.get('explanation', '')}",
                "",
            ]

    if gold_cases:
        lines += [f"## Gold Cases ({len(gold_cases)})", ""]
        for i, gc in enumerate(gold_cases, 1):
            lines += [
                f"### {i}.",
                f"- **EN:** {gc.get('excellent_translation', '')}",
                f"- **Why:** {gc.get('why_good', '')}",
                "",
            ]

    if updates:
        lines += [f"## Proposed Asset Updates ({len(updates)})", "",
                  "_Nothing has been applied. Review each entry, then apply manually._", ""]
        for i, u in enumerate(updates, 1):
            conf = u.get("confidence", 0)
            target = ASSET_FILE_MAP.get(u.get("target_file", ""), u.get("target_file", "?"))
            lines += [
                f"### {i}. → {target}  (conf={conf:.2f}, action={u.get('action','?')})",
                f"**Reason:** {u.get('reason', '')}",
                "",
                "```",
                u.get("content", "").strip(),
                "```",
                "",
            ]
    else:
        lines += ["## Proposed Asset Updates", "", "_None this round._", ""]

    staging_path.write_text("\n".join(lines), encoding="utf-8")
    return staging_path


def print_round_report(round_num: int, eval_report: dict) -> None:
    score = eval_report.get("score", "?")
    breakdown = eval_report.get("score_breakdown", {})
    bad_cases = eval_report.get("bad_cases", [])
    gold_cases = eval_report.get("gold_cases", [])
    updates = eval_report.get("proposed_asset_updates", [])
    summary = eval_report.get("summary", "")

    sep = "─" * 60
    print(f"\n{sep}")
    print(f"  ROUND {round_num:03d} REPORT")
    print(sep)
    print(f"  Quality score : {score}/10  "
          f"(accuracy={breakdown.get('accuracy','?')}  "
          f"fluency={breakdown.get('fluency','?')}  "
          f"elegance={breakdown.get('elegance','?')})")
    print(f"  Summary       : {summary}")
    print()

    if bad_cases:
        print(f"  BAD CASES ({len(bad_cases)}):")
        for i, bc in enumerate(bad_cases, 1):
            sev = bc.get("severity", "?")
            btype = bc.get("type", "?")
            print(f"    {i}. [{sev.upper()}] {btype}")
            print(f"       ZH: {bc.get('chinese_original', '')[:80]}")
            print(f"       EN: {bc.get('bad_translation', '')[:80]}")
            print(f"       Fix: {bc.get('suggested_fix', '')[:80]}")
        print()

    if gold_cases:
        print(f"  GOLD CASES ({len(gold_cases)}):")
        for i, gc in enumerate(gold_cases, 1):
            print(f"    {i}. {gc.get('excellent_translation', '')[:100]}")
            print(f"       Why: {gc.get('why_good', '')[:80]}")
        print()

    if updates:
        print(f"  PROPOSED ASSET UPDATES ({len(updates)}) — staged for review:")
        for i, u in enumerate(updates, 1):
            conf = u.get("confidence", 0)
            print(f"    {i}. [conf={conf:.2f}] → {u.get('target_file', '?')}")
            print(f"       {u.get('content', '')[:100]}")
        print()

    print(sep)


def generate_convergence_report(state: dict, batch: int) -> Path:
    rounds = [r for r in state["rounds"] if r.get("batch") == batch]
    if not rounds:
        rounds = state["rounds"]

    scores = [r["score"] for r in rounds if "score" in r]
    bad_counts = [r["bad_count"] for r in rounds if "bad_count" in r]
    gold_counts = [r["gold_count"] for r in rounds if "gold_count" in r]
    total_staged = sum(r.get("staged", 0) for r in rounds)

    scores = [s for s in scores if s is not None]
    trend = "improving" if len(scores) > 1 and scores[-1] > scores[0] else \
            "stable" if len(scores) > 1 and abs(scores[-1] - scores[0]) < 0.5 else \
            "needs more work"

    staging_files = [r["staging"] for r in rounds if r.get("staging")]

    report = textwrap.dedent(f"""\
        # Quality Loop — Batch {batch} Convergence Report
        Generated: {datetime.now(timezone.utc).isoformat()}

        ## Summary
        - Rounds completed: {len(rounds)}
        - Score trend: {scores[0] if scores else '?'} → {scores[-1] if scores else '?'} ({trend})
        - Total bad cases found: {sum(bad_counts)}
        - Total gold cases found: {sum(gold_counts)}
        - Proposed updates staged for review: {total_staged}

        ## Round Scores
        {chr(10).join(f'  Round {r["round"]:03d}: {r.get("score","?")}/10 '
                      f'(bad={r.get("bad_count","?")}, gold={r.get("gold_count","?")})'
                      for r in rounds)}

        ## Pending Review
        {chr(10).join(f'  {p}' for p in staging_files)}

        ## Recommendation
        {"✅ Quality is improving — continue to next batch." if trend == "improving"
         else "⚠️  Quality has plateaued — review staging files before next batch."
         if trend == "stable"
         else "🔴 Quality needs significant work — inspect bad cases and update prompts."}

        ## Next Steps
        - Read staging files above; apply approved entries to project_assets/ manually
        - Run: python scripts/quality_loop.py --rounds 3 --continue
          (after applying any asset updates)
    """)

    report_path = LOOP_DIR / f"convergence_batch_{batch:02d}.md"
    report_path.write_text(report, encoding="utf-8")
    return report_path


# ── Main loop ─────────────────────────────────────────────────────────────────

def main() -> int:
    ap = argparse.ArgumentParser(description="Run quality iteration loop.")
    ap.add_argument("--rounds", type=int, default=10)
    ap.add_argument("--source", type=Path, default=DEFAULT_SOURCE)
    ap.add_argument("--model-profile", default=DEFAULT_PROFILE)
    ap.add_argument("--book-memory", type=Path, default=DEFAULT_BOOK_MEMORY)
    ap.add_argument("--continue", dest="resume", action="store_true",
                    help="Continue from last saved state (don't bump the batch counter)")
    ap.add_argument("--reset", action="store_true",
                    help="Destructive: wipe state.json and start fresh batch 1, round 1")
    ap.add_argument("--evaluator", choices=["claude", "deepseek", "auto"],
                    default="auto",
                    help="Forwarded to evaluate_translation.py. 'auto' (default) "
                         "tries Claude and falls back to DeepSeek on confirmed "
                         "rate-limit; 'claude' / 'deepseek' lock to one backend.")
    ap.add_argument("--human-review", type=Path,
                    help="Optional markdown file forwarded to "
                         "evaluate_translation.py as must-check calibration "
                         "signals.")
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    LOOP_DIR.mkdir(parents=True, exist_ok=True)

    # Always load existing state unless --reset is explicitly passed.
    # The previous behaviour (load only on --resume, else fresh dict) silently
    # threw away the cross-batch rounds[] history and reset the round counter,
    # which clobbered prior round_NNN directories on the next default run.
    fresh_state = {
        "batch": 0,
        "total_rounds": 0,
        "rounds": [],
        "started_at": datetime.now(timezone.utc).isoformat(),
    }
    if args.reset:
        state = fresh_state
    elif STATE_FILE.exists():
        state = load_state()
    else:
        state = fresh_state

    if not args.resume:
        state["batch"] = state.get("batch", 0) + 1

    batch = state["batch"]
    start_round = state["total_rounds"] + 1

    print(f"\n{'═' * 60}")
    print(f"  QUALITY LOOP — Batch {batch}, Rounds {start_round}–{start_round + args.rounds - 1}")
    print(f"  Source   : {args.source}")
    print(f"  Profile  : {args.model_profile}")
    print(f"{'═' * 60}\n")

    if not args.source.exists():
        sys.exit(f"quality_loop: source not found: {args.source}")
    if args.human_review and not args.human_review.exists():
        sys.exit(f"quality_loop: human review not found: {args.human_review}")

    python = PROJECT_ROOT / "venv" / "bin" / "python"
    if not python.exists():
        python = Path(sys.executable)

    for i in range(args.rounds):
        round_num = start_round + i
        rdir = round_dir(round_num)
        rdir.mkdir(parents=True, exist_ok=True)
        output_path = rdir / "output.md"
        eval_path = rdir / "eval.json"

        print(f"\n{'─' * 60}")
        print(f"  Round {round_num:03d} / {start_round + args.rounds - 1}")
        print(f"{'─' * 60}")

        # Step 1: Translate
        cli_cmd = [
            str(python), "-m", "app.cli", "chapter", "run",
            "--source", str(args.source),
            "--output", str(output_path),
            "--model-profile", args.model_profile,
        ]
        if args.book_memory.exists():
            cli_cmd += ["--book-memory", str(args.book_memory)]

        result = run(cli_cmd, "translate", dry_run=args.dry_run)
        if result.returncode != 0 and not args.dry_run:
            print(f"  Translation failed — skipping round {round_num}")
            continue

        # Step 2: Evaluate
        eval_cmd = [
            str(python), str(PROJECT_ROOT / "scripts" / "evaluate_translation.py"),
            "--source", str(args.source),
            "--translation", str(output_path),
            "--assets-dir", str(ASSETS_DIR),
            "--output", str(eval_path),
            "--evaluator", args.evaluator,
        ]
        if args.human_review:
            eval_cmd += ["--human-review", str(args.human_review)]
        if args.dry_run:
            eval_cmd.append("--dry-run")

        run(eval_cmd, "evaluate", dry_run=False)  # always run evaluator cmd itself

        # Step 3: Parse eval, write staging file — nothing touches project_assets/
        eval_report: dict = {}
        if eval_path.exists():
            try:
                eval_report = json.loads(eval_path.read_text())
            except json.JSONDecodeError:
                print(f"  Could not parse eval report — skipping staging")

        print_round_report(round_num, eval_report)

        staging_path = write_staging_file(rdir, eval_report, round_num)
        n_staged = len(eval_report.get("proposed_asset_updates", []))
        print(f"  → Staged {n_staged} proposed update(s) for review: {staging_path}")

        # Step 4: Save round state
        round_state = {
            "round": round_num,
            "batch": batch,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "score": eval_report.get("score"),
            "bad_count": len(eval_report.get("bad_cases", [])),
            "gold_count": len(eval_report.get("gold_cases", [])),
            "staged": n_staged,
            "backend": eval_report.get("backend", "unknown"),
            "output": str(output_path),
            "eval": str(eval_path),
            "staging": str(staging_path),
        }
        state["rounds"].append(round_state)
        state["total_rounds"] = round_num
        save_state(state)

    # Batch complete — generate convergence report
    report_path = generate_convergence_report(state, batch)
    print(f"\n{'═' * 60}")
    print(f"  BATCH {batch} COMPLETE")
    print(f"{'═' * 60}")
    print(f"\n  Convergence report → {report_path}")
    print(f"\n  Read staging files in data/quality_loop/round_*/staging.md")
    print(f"  Apply approved entries to project_assets/ manually, then:")
    print(f"    a) python scripts/quality_loop.py --rounds 3 --continue")
    print(f"       (next batch with updated assets)")
    print(f"    b) Inspect bad cases and adjust prompts first")
    print(f"    c) Done — move to a new chapter")
    print()

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
