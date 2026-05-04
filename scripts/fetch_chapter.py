#!/usr/bin/env python3
"""Fetch chapters from 52shuku.net and save to data/source/.

Usage:
  python scripts/fetch_chapter.py --page 2
  python scripts/fetch_chapter.py --pages 2-4
  python scripts/fetch_chapter.py --page 2 --output data/source/chapter_01.txt
"""
from __future__ import annotations

import argparse
import re
import subprocess
import sys
from pathlib import Path

BASE_URL = "https://www.52shuku.net/yanqing/12_b/bjTZL_{}.html"
PROJECT_ROOT = Path(__file__).parent.parent
NOISE_PATTERNS = [
    r"52书库", r"52shuku", r"收藏网址", r"推荐给朋友", r"拜托啦",
    r"同类言情", r"小说推荐", r"完结\+番外", r"在线阅读_52",
]


def fetch_raw_html(page_num: int) -> str:
    url = BASE_URL.format(page_num)
    result = subprocess.run(
        ["curl", "-s", "--max-time", "30", "-A",
         "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36",
         url],
        capture_output=True, text=True,
    )
    if result.returncode != 0:
        sys.exit(f"fetch_chapter: curl failed for page {page_num}: {result.stderr}")
    return result.stdout


def html_to_text(html: str) -> str:
    # Extract only the novel-text div to avoid noise patterns in the page header/title
    m = re.search(r'id="text"[^>]*>(.*?)</div>', html, flags=re.DOTALL)
    if m:
        html = m.group(1)
    html = re.sub(r"<script[^>]*>.*?</script>", "", html, flags=re.DOTALL)
    html = re.sub(r"<style[^>]*>.*?</style>", "", html, flags=re.DOTALL)
    text = re.sub(r"<[^>]+>", "\n", html)
    text = re.sub(r"\n{3,}", "\n\n", text)
    lines = [l.strip() for l in text.split("\n") if l.strip()]
    # Skip intro/synopsis lines — collect from the first chapter heading onward
    in_novel = False
    novel_lines: list[str] = []
    for line in lines:
        if not in_novel and re.search(r"^第[一二三四五六七八九十百千\d]+章", line):
            in_novel = True
        if not in_novel:
            continue
        if any(re.search(p, line) for p in NOISE_PATTERNS):
            break
        novel_lines.append(line)
    return "\n\n".join(novel_lines)


def fetch_page(page_num: int) -> str:
    html = fetch_raw_html(page_num)
    text = html_to_text(html)
    if not text:
        sys.exit(f"fetch_chapter: no content extracted from page {page_num}")
    return text


def main() -> int:
    ap = argparse.ArgumentParser(description="Fetch chapters from 52shuku.net")
    group = ap.add_mutually_exclusive_group(required=True)
    group.add_argument("--page", type=int, help="Single page number (page 2 = chapter 1-2)")
    group.add_argument("--pages", help="Page range, e.g. 2-5")
    ap.add_argument("--output", type=Path, help="Output file (default: data/source/page_{N}.txt)")
    ap.add_argument("--dry-run", action="store_true", help="Print extracted text, don't save")
    args = ap.parse_args()

    if args.page:
        pages = [args.page]
    else:
        start, end = args.pages.split("-")
        pages = list(range(int(start), int(end) + 1))

    chunks: list[str] = []
    for p in pages:
        print(f"fetch_chapter: fetching page {p}...", file=sys.stderr)
        chunks.append(fetch_page(p))

    content = "\n\n".join(chunks)

    if args.dry_run:
        print(content)
        return 0

    if args.output:
        out_path = args.output
    elif len(pages) == 1:
        out_path = PROJECT_ROOT / "data" / "source" / f"page_{pages[0]:04d}.txt"
    else:
        out_path = PROJECT_ROOT / "data" / "source" / f"pages_{pages[0]:04d}-{pages[-1]:04d}.txt"

    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(content, encoding="utf-8")
    print(f"fetch_chapter: saved {len(content)} chars → {out_path}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
