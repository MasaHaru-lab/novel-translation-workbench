#!/usr/bin/env python3
import sys
sys.path.insert(0, '.')
from app.translate.schema import TranslationInput
from app.translate.translator import build_review_prompt
from debug_review_step import DEFAULT_SAMPLE

source_text = DEFAULT_SAMPLE
input = TranslationInput(
    segment_id='debug',
    source_text=source_text,
    glossary_terms=[]
)

# Simulate draft translation (just placeholder)
draft_text = "This is a placeholder draft translation."

prompt = build_review_prompt(input, draft_text, assets_mode="full")
print("=== PROMPT LENGTH ===")
print("Characters:", len(prompt))
print("Lines:", prompt.count('\n'))
print("Approx tokens (chars/4):", len(prompt)//4)
print("=== FIRST 1000 CHARS ===")
print(prompt[:1000])
print("=== LAST 1000 CHARS ===")
print(prompt[-1000:])
print("=== DUPLICATION CHECK ===")
# Check if any line repeats many times
lines = prompt.splitlines()
line_counts = {}
for line in lines:
    line_counts[line] = line_counts.get(line, 0) + 1
for line, count in line_counts.items():
    if count > 2 and line.strip():
        print(f"Repeats {count} times: {line[:80]}...")
        break
else:
    print("No excessive duplication")

# Also print assets block
from app.translate.translator import build_project_assets_block
assets = build_project_assets_block("full")
print("\n=== ASSETS BLOCK LENGTH ===")
print("Assets chars:", len(assets))
print("Assets lines:", assets.count('\n'))
print("--- First 500 chars ---")
print(assets[:500])