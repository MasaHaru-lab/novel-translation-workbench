#!/usr/bin/env python3
"""
Debug review_translate: print draft and polished side by side.
"""
import os
import sys

sys.path.insert(0, os.path.dirname(__file__))

from app.translate.schema import TranslationInput, GlossaryTerm
from app.translate.translator import translate_draft, polish_translation

DEFAULT_SAMPLE = """秦流西见状抬腿要走，秦老太太叫住了她。

　　“西丫头，你也留下来听听。”

　　秦流西脚步一顿，重新坐了下来，端起了一杯茶。

　　第十四章 小人作崇所为

　　“西丫头，你小时候身子骨不行，时常生病，是与秦家冲煞所致，那赤元老道说你命格奇诡，故而早早早把你记在你嫡母名下，以你嫡母的清贵给你压一压，再离家过活，如此才可皆大欢喜，这才把你送回老宅。祖母知你心里有怨，怨我们把你放在老宅养着十年，可这也是为彼此好的事。”"""

def main():
    backend_url = os.environ.get('MODEL_BACKEND_URL', '')
    if not backend_url:
        sys.stderr.write("ERROR: MODEL_BACKEND_URL not set\n")
        sys.exit(1)

    source_text = DEFAULT_SAMPLE
    input = TranslationInput(
        segment_id='debug',
        source_text=source_text,
        glossary_terms=[]
    )

    draft_output = translate_draft(input)
    print("=== DRAFT ===")
    print(draft_output.draft_translation)
    print("=== END DRAFT ===\n")

    polished_output = polish_translation(input, draft_output)
    print("=== POLISHED ===")
    print(polished_output.polished_translation)
    print("=== END POLISHED ===\n")

    print("=== COMPARISON ===")
    if draft_output.draft_translation == polished_output.polished_translation:
        print("IDENTICAL")
    else:
        print("DIFFERENT")
        # Show diff lines
        dlines = draft_output.draft_translation.splitlines()
        plines = polished_output.polished_translation.splitlines()
        for i, (d, p) in enumerate(zip(dlines, plines)):
            if d != p:
                print(f"Line {i}:")
                print(f"  D: {d}")
                print(f"  P: {p}")
        if len(dlines) != len(plines):
            print(f"Line count diff: draft {len(dlines)} vs polished {len(plines)}")

if __name__ == '__main__':
    main()