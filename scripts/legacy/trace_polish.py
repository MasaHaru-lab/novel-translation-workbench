#!/usr/bin/env python3
"""
Trace one real polish run end-to-end.
Prints each stage to identify where polish collapses into identity.
"""
import os
import sys
import logging

logging.basicConfig(level=logging.INFO, format='%(message)s')
logger = logging.getLogger()

# Add app to path
sys.path.insert(0, os.path.dirname(__file__))

from app.translate.schema import TranslationInput, GlossaryTerm
from app.translate.translator import (
    translate_draft,
    run_internal_review_with_backend,
    parse_review_findings,
    translate_polish_with_backend,
    clean_polished_output,
    build_review_prompt,
    build_polish_prompt,
)

# Same sample as review_translate.py
DEFAULT_SAMPLE = """秦流西见状抬腿要走，秦老太太叫住了她。

　　“西丫头，你也留下来听听。”

　　秦流西脚步一顿，重新坐了下来，端起了一杯茶。

　　第十四章 小人作崇所为

　　“西丫头，你小时候身子骨不行，时常生病，是与秦家冲煞所致，那赤元老道说你命格奇诡，故而早早就把你记在你嫡母名下，以你嫡母的清贵给你压一压，再离家过活，如此才可皆大欢喜，这才把你送回老宅。祖母知你心里有怨，怨我们把你放在老宅养着十年，可这也是为彼此好的事。”"""

def get_input_text():
    """Return source text to translate.
    If a file path is provided as command-line argument, read from that file.
    Otherwise use the default sample.
    """
    if len(sys.argv) > 1:
        filepath = sys.argv[1]
        try:
            with open(filepath, 'r', encoding='utf-8') as f:
                return f.read()
        except Exception as e:
            logger.error(f"Could not read {filepath}: {e}")
            logger.error("Using default sample.")
            return DEFAULT_SAMPLE
    else:
        return DEFAULT_SAMPLE

def main():
    # Check backend URL
    backend_url = os.environ.get('MODEL_BACKEND_URL', '')
    if not backend_url:
        logger.error("ERROR: MODEL_BACKEND_URL environment variable not set.")
        logger.error("Set it to a working backend URL, e.g.:")
        logger.error("  export MODEL_BACKEND_URL=http://192.168.68.61:8001/generate")
        sys.exit(1)

    logger.info(f"Using backend: {backend_url}")

    source_text = get_input_text()
    logger.info(f"Source text length: {len(source_text)} chars")
    logger.info(f"First 200 chars: {source_text[:200]}...")

    # Create translation input
    input = TranslationInput(
        segment_id='trace_sample',
        source_text=source_text,
        glossary_terms=[]
    )

    # Step 1: Draft translation
    logger.info("\n=== 1. Draft translation ===")
    draft_output = translate_draft(input)
    draft_text = draft_output.draft_translation
    logger.info(f"Draft length: {len(draft_text)} chars")
    logger.info(f"Draft preview: {draft_text[:200]}...")
    logger.info("--- Full draft ---")
    logger.info(draft_text)
    logger.info("--- End draft ---")

    # Step 2: Build review prompt
    logger.info("\n=== 2. Build review prompt (Prompt B) ===")
    review_prompt = build_review_prompt(input, draft_text, assets_mode="full")
    logger.info(f"Review prompt length: {len(review_prompt)} chars")
    logger.info("--- Review prompt ---")
    logger.info(review_prompt)
    logger.info("--- End review prompt ---")

    # Step 3: Internal review with backend
    logger.info("\n=== 3. Internal review with backend ===")
    review_raw = run_internal_review_with_backend(input, draft_text, assets_mode="full")
    logger.info(f"Raw review response length: {len(review_raw)} chars")
    logger.info("--- Raw review response ---")
    logger.info(review_raw)
    logger.info("--- End raw review ---")

    # Step 4: Parse review findings
    logger.info("\n=== 4. Parse review findings ===")
    findings = parse_review_findings(review_raw)
    logger.info(f"major_issue: {findings.major_issue}")
    logger.info(f"why_it_matters: {findings.why_it_matters}")
    logger.info(f"recommended_fix: {findings.recommended_fix}")
    logger.info(f"optional_notes: {findings.optional_notes}")
    logger.info(f"has_major_issue(): {findings.has_major_issue()}")

    # Step 5: Determine if revision is triggered
    logger.info("\n=== 5. Revision decision ===")
    if findings.has_major_issue():
        logger.info("Revision IS triggered (major issue found)")
        # Step 6: Build polish prompt with review guidance
        logger.info("\n=== 6. Build polish prompt (Prompt A with guidance) ===")
        polish_prompt = build_polish_prompt(input, draft_text, assets_mode="full", review_guidance=findings)
        logger.info(f"Polish prompt length: {len(polish_prompt)} chars")
        logger.info("--- Polish prompt ---")
        logger.info(polish_prompt)
        logger.info("--- End polish prompt ---")

        # Step 7: Call backend for polish
        logger.info("\n=== 7. Polish with backend ===")
        polished_text_raw = translate_polish_with_backend(input, draft_text, assets_mode="full", review_guidance=findings)
        logger.info(f"Raw polished text length: {len(polished_text_raw)} chars")
        logger.info("--- Raw polished text ---")
        logger.info(polished_text_raw)
        logger.info("--- End raw polished text ---")

        # Step 8: Clean polished output
        logger.info("\n=== 8. Clean polished output ===")
        polished_text = clean_polished_output(polished_text_raw)
        logger.info(f"Cleaned polished length: {len(polished_text)} chars")
        logger.info("--- Cleaned polished text ---")
        logger.info(polished_text)
        logger.info("--- End cleaned polished ---")
    else:
        logger.info("Revision NOT triggered (no major issue)")
        polished_text = draft_text
        logger.info("Polished text set to draft text (identical)")

    # Step 9: Final comparison
    logger.info("\n=== 9. Final comparison ===")
    logger.info(f"Draft length: {len(draft_text)}")
    logger.info(f"Polished length: {len(polished_text)}")
    logger.info(f"Are they identical? {draft_text == polished_text}")
    if draft_text == polished_text:
        logger.info("WARNING: Draft and polished are identical!")
        # Determine cause
        if not findings.has_major_issue():
            logger.info("Cause: reviewer reported no major issue.")
        else:
            logger.info("Cause: reviewer reported major issue but polished text still matches draft.")
            logger.info("Possible reasons:")
            logger.info("  - Backend ignored revision prompt")
            logger.info("  - Cleaning step collapsed output back to draft")
            logger.info("  - Parser dropped the issue")
            logger.info("  - Revision step skipped despite has_major_issue()")
    else:
        logger.info("SUCCESS: Draft and polished are different.")
        logger.info("Difference preview (first diff):")
        # Simple diff: find first differing line
        draft_lines = draft_text.splitlines()
        polished_lines = polished_text.splitlines()
        for i, (d, p) in enumerate(zip(draft_lines, polished_lines)):
            if d != p:
                logger.info(f"Line {i}:")
                logger.info(f"  Draft:     {d}")
                logger.info(f"  Polished:  {p}")
                break
        else:
            if len(draft_lines) != len(polished_lines):
                logger.info(f"Line count differs: draft {len(draft_lines)} vs polished {len(polished_lines)}")

    logger.info("\n=== Trace complete ===")

if __name__ == '__main__':
    main()