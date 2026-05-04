#!/usr/bin/env python3
"""Quality iteration loop for novel-translation-workbench.

Runs N rounds of: translate → evaluate → auto-apply high-confidence asset updates.
Pauses for human review after each batch.

Usage:
  python scripts/quality_loop.py --rounds 10
  python scripts/quality_loop.py --rounds 10 --continue   # resume after checkpoint
  python scripts/quality_loop.py --rounds 10 --dry-run    # verify pipeline, no API calls
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

AUTO_APPLY_THRESHOLD = 0.80  # confidence >= this → auto-apply asset update


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


def apply_asset_update(update: dict) -> bool:
    target_file = ASSETS_DIR / update["target_file"]
    action = update["action"]
    content = update["content"].strip()

    if action == "add":
        existing = target_file.read_text(encoding="utf-8") if target_file.exists() else ""
        if content in existing:
            return False  # already present
        with target_file.open("a", encoding="utf-8") as f:
            f.write(f"\n\n{content}\n")
        return True

    if action == "modify":
        # Append as a note; full modify requires human review
        existing = target_file.read_text(encoding="utf-8") if target_file.exists() else ""
        note = f"\n\n<!-- AUTO-UPDATE {datetime.now(timezone.utc).date()} -->\n{content}\n"
        if content in existing:
            return False
        target_file.write_text(existing + note, encoding="utf-8")
        return True

    return False  # "remove" always needs human review


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
        print(f"  PROPOSED ASSET UPDATES ({len(updates)}):")
        for i, u in enumerate(updates, 1):
            conf = u.get("confidence", 0)
            auto = "AUTO" if conf >= AUTO_APPLY_THRESHOLD else "REVIEW"
            print(f"    {i}. [{auto} conf={conf:.2f}] → {u['target_file']}")
            print(f"       {u.get('content', '')[:100]}")
            print(f"       Reason: {u.get('reason', '')[:80]}")
        print()

    print(sep)


def generate_convergence_report(state: dict, batch: int) -> Path:
    rounds = [r for r in state["rounds"] if r.get("batch") == batch]
    if not rounds:
        rounds = state["rounds"]

    scores = [r["score"] for r in rounds if "score" in r]
    bad_counts = [r["bad_count"] for r in rounds if "bad_count" in r]
    gold_counts = [r["gold_count"] for r in rounds if "gold_count" in r]
    updates_applied = sum(r.get("updates_applied", 0) for r in rounds)

    scores = [s for s in scores if s is not None]
    trend = "improving" if len(scores) > 1 and scores[-1] > scores[0] else \
            "stable" if len(scores) > 1 and abs(scores[-1] - scores[0]) < 0.5 else \
            "needs more work"

    report = textwrap.dedent(f"""\
        # Quality Loop — Batch {batch} Convergence Report
        Generated: {datetime.now(timezone.utc).isoformat()}

        ## Summary
        - Rounds completed: {len(rounds)}
        - Score trend: {scores[0] if scores else '?'} → {scores[-1] if scores else '?'} ({trend})
        - Total bad cases found: {sum(bad_counts)}
        - Total gold cases found: {sum(gold_counts)}
        - Asset updates auto-applied: {updates_applied}

        ## Round Scores
        {chr(10).join(f'  Round {r["round"]:03d}: {r.get("score","?")}/10 '
                      f'(bad={r.get("bad_count","?")}, gold={r.get("gold_count","?")})'
                      for r in rounds)}

        ## Recommendation
        {"✅ Quality is improving — continue to next batch." if trend == "improving"
         else "⚠️  Quality has plateaued — review asset updates manually before next batch."
         if trend == "stable"
         else "🔴 Quality needs significant work — inspect bad cases and update prompts."}

        ## Next Steps
        - Review bad cases in data/quality_loop/round_*/eval.json
        - Check auto-applied asset updates in project_assets/
        - Run: python scripts/quality_loop.py --rounds 10 --continue
          (or adjust prompts first if plateau)
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
                    help="Continue from last saved state")
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    LOOP_DIR.mkdir(parents=True, exist_ok=True)
    state = load_state() if args.resume else {
        "batch": 0,
        "total_rounds": 0,
        "rounds": [],
        "started_at": datetime.now(timezone.utc).isoformat(),
    }

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
        ]
        if args.dry_run:
            eval_cmd.append("--dry-run")

        run(eval_cmd, "evaluate", dry_run=False)  # always run evaluator cmd itself

        # Step 3: Parse eval and apply high-confidence updates
        eval_report: dict = {}
        if eval_path.exists():
            try:
                eval_report = json.loads(eval_path.read_text())
            except json.JSONDecodeError:
                print(f"  Could not parse eval report — skipping asset updates")

        print_round_report(round_num, eval_report)

        updates_applied = 0
        review_needed: list[dict] = []
        for update in eval_report.get("proposed_asset_updates", []):
            conf = update.get("confidence", 0)
            if conf >= AUTO_APPLY_THRESHOLD and not args.dry_run:
                applied = apply_asset_update(update)
                if applied:
                    updates_applied += 1
                    print(f"  ✓ Auto-applied: {update['target_file']} — {update['content'][:60]}")
            else:
                review_needed.append(update)

        if review_needed:
            print(f"\n  ⚠  {len(review_needed)} update(s) need human review:")
            for u in review_needed:
                print(f"     [{u['target_file']}] {u.get('content', '')[:80]}")

        # Step 4: Save round state
        round_state = {
            "round": round_num,
            "batch": batch,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "score": eval_report.get("score"),
            "bad_count": len(eval_report.get("bad_cases", [])),
            "gold_count": len(eval_report.get("gold_cases", [])),
            "updates_applied": updates_applied,
            "updates_pending_review": len(review_needed),
            "output": str(output_path),
            "eval": str(eval_path),
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
    print(f"\n  Review the report, then decide:")
    print(f"    a) python scripts/quality_loop.py --rounds 10 --continue")
    print(f"       (next batch with updated assets)")
    print(f"    b) Inspect bad cases and adjust prompts first")
    print(f"    c) Done — move to a new chapter")
    print()

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
