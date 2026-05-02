#!/usr/bin/env python3
import sys
sys.path.insert(0, '.')
import tiktoken
from app.translate.schema import TranslationInput
from app.translate.translator import build_review_prompt, build_draft_prompt, build_polish_prompt
from app.translate.project_context import load_all_assets, load_prompt

# Load full chapter
with open('one_chapter.txt', 'r', encoding='utf-8') as f:
    chapter = f.read()
# Remove trailing commands (after line 80)
lines = chapter.splitlines()
# Keep only lines before the command lines
content_lines = []
for line in lines:
    if line.startswith('./venv/bin/python'):
        break
    content_lines.append(line)
chapter = '\n'.join(content_lines)

print(f"Chapter characters: {len(chapter)}")
print(f"Chapter lines: {len(content_lines)}")

# Create input
input = TranslationInput(
    segment_id='full',
    source_text=chapter,
    glossary_terms=[]
)

# Simulate draft translation (just placeholder same length)
draft_text = 'a' * len(chapter)  # placeholder

# Build prompts
draft_prompt = build_draft_prompt(input, assets_mode="full")
review_prompt = build_review_prompt(input, draft_text, assets_mode="full")
polish_prompt = build_polish_prompt(input, draft_text, assets_mode="full")

# Encode
enc = tiktoken.get_encoding("cl100k_base")
draft_tokens = len(enc.encode(draft_prompt))
review_tokens = len(enc.encode(review_prompt))
polish_tokens = len(enc.encode(polish_prompt))

print(f"Draft prompt tokens: {draft_tokens}")
print(f"Review prompt tokens: {review_tokens}")
print(f"Polish prompt tokens: {polish_tokens}")

# Compute assets block tokens
from app.translate.translator import build_project_assets_block
assets_block = build_project_assets_block("full")
assets_tokens = len(enc.encode(assets_block))
print(f"Assets block tokens: {assets_tokens}")

# Compute prompt A tokens
prompt_a = load_prompt("prompt_a")
prompt_a_tokens = len(enc.encode(prompt_a))
print(f"Prompt A tokens: {prompt_a_tokens}")
prompt_b = load_prompt("prompt_b")
prompt_b_tokens = len(enc.encode(prompt_b))
print(f"Prompt B tokens: {prompt_b_tokens}")

# Estimate total tokens requested if max_tokens default is 4096
max_tokens_default = 4096
total_requested_review = review_tokens + max_tokens_default
print(f"Total tokens with max_tokens={max_tokens_default}: {total_requested_review}")
print(f"Overshoot vs 102400: {total_requested_review - 102400}")

# Try to find max_tokens such that total = 102823
# total = review_tokens + max_tokens = 102823
max_tokens = 102823 - review_tokens
print(f"Implied max_tokens from error: {max_tokens}")
print(f"Implied prompt tokens from error: {102823 - max_tokens}")

# If max_tokens is default 102400, prompt tokens = 102823 - 102400 = 423
print(f"If max_tokens=102400, prompt tokens = {102823 - 102400}")
print(f"That's plausible? review_tokens = {review_tokens}")
print(f"Ratio review_tokens/423: {review_tokens/423:.1f}")

# Print sections lengths
def section_lengths(prompt):
    lines = prompt.splitlines()
    sections = {}
    current = []
    for line in lines:
        if line.startswith('## ') and current:
            sections['\n'.join(current)] = len(enc.encode('\n'.join(current)))
            current = []
        current.append(line)
    if current:
        sections['\n'.join(current)] = len(enc.encode('\n'.join(current)))
    return sections

print("\nReview prompt sections:")
for section, count in section_lengths(review_prompt).items():
    print(f"{count} tokens: {section[:100]}...")