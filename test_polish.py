#!/usr/bin/env python3
"""
Minimal test of the new polish implementation.
Requires MODEL_BACKEND_URL environment variable set to a working backend.
"""
import os
import sys

# Add app to path
sys.path.insert(0, os.path.dirname(__file__))

from app.translate.schema import TranslationInput, GlossaryTerm
from app.translate.translator import translate_draft, polish_translation

REAL_SEGMENT = """秦流西见状抬腿要走，秦老太太叫住了她。

　　“西丫头，你也留下来听听。”

　　秦流西脚步一顿，重新坐了下来，端起了一杯茶。

　　第十四章 小人作崇所为

　　“西丫头，你小时候身子骨不行，时常生病，是与秦家冲煞所致，那赤元老道说你命格奇诡，故而早早就把你记在你嫡母名下，以你嫡母的清贵给你压一压，再离家过活，如此才可皆大欢喜，这才把你送回老宅。祖母知你心里有怨，怨我们把你放在老宅养着十年，可这也是为彼此好的事。”"""



def main():
    # Check backend URL
    backend_url = os.environ.get('MODEL_BACKEND_URL', '')
    if not backend_url:
        print("ERROR: MODEL_BACKEND_URL environment variable not set.")
        print("Set it to a working backend URL, e.g.:")
        print("  export MODEL_BACKEND_URL=http://192.168.68.61:8001/generate")
        sys.exit(1)

    print(f"Using backend: {backend_url}")

    # Create test input with real segment
    input = TranslationInput(
        segment_id='real_segment_test',
        source_text=REAL_SEGMENT,
        glossary_terms=[]
    )


    # Draft translation (real backend call)
    print("\n=== Draft Translation ===")
    draft_output = translate_draft(input)
    print(f"Draft length: {len(draft_output.draft_translation)} chars")
    print(f"Draft preview: {draft_output.draft_translation[:200]}...")

    # Validate draft is real (not mock)
    if draft_output.draft_translation.strip() == "":
        print("ERROR: Draft translation is empty!")
        sys.exit(1)
    if "[DRAFT ENGLISH]" in draft_output.draft_translation:
        print("ERROR: Draft still contains mock pattern '[DRAFT ENGLISH]'")
        print("This indicates translate_draft() is still returning mock output.")
        sys.exit(1)

    # Polish translation (real backend call)
    print("\n=== Polish Translation ===")
    try:
        polished_output = polish_translation(input, draft_output)
        print(f"Polished length: {len(polished_output.polished_translation)} chars")
        print(f"Polished preview: {polished_output.polished_translation[:200]}...")

        # Validate polished is real and non-empty
        if polished_output.polished_translation.strip() == "":
            print("ERROR: Polished translation is empty!")
            sys.exit(1)

        # Check for explanatory text markers
        markers = ["explanation:", "note:", "notes:", "alternative:", "alternatives:", "commentary:", "comment:"]
        polished_lower = polished_output.polished_translation.lower()
        for marker in markers:
            if marker in polished_lower:
                print(f"ERROR: Polished translation contains explanatory marker '{marker}'!")
                print("This indicates the model returned explanation/notes/alternatives instead of just the polished translation.")
                sys.exit(1)

        # Compare
        print("\n=== Comparison ===")
        print(f"Draft length: {len(draft_output.draft_translation)} chars")
        print(f"Polished length: {len(polished_output.polished_translation)} chars")
        print(f"Length difference: {len(polished_output.polished_translation) - len(draft_output.draft_translation)} chars")

        if draft_output.draft_translation == polished_output.polished_translation:
            print("WARNING: Draft and polished are identical!")
            print("This may indicate:")
            print("  - Backend returned same text as draft")
            print("  - Backend is not processing polish prompt correctly")
        else:
            print("SUCCESS: Draft and polished are different (as expected).")
            print("Difference indicates real second-pass processing.")

    except Exception as e:
        print(f"ERROR: Polish failed: {e}")
        print("\nTraceback:")
        import traceback
        traceback.print_exc()
        sys.exit(1)

if __name__ == '__main__':
    main()