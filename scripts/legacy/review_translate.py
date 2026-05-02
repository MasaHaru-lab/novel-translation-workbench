#!/usr/bin/env python3
"""
Minimal review-mode translation output.
Only prints the final polished translation text, no explanations, comparisons, or status messages.
"""
import os
import sys

# Add app to path
sys.path.insert(0, os.path.dirname(__file__))

from app.translate.schema import TranslationInput, GlossaryTerm
from app.translate.translator import translate_draft, polish_translation

# Default sample text (same as test_polish.py)
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
            # Fall back to default sample
            sys.stderr.write(f"Could not read {filepath}: {e}\n")
            sys.stderr.write("Using default sample.\n")
            return DEFAULT_SAMPLE
    else:
        return DEFAULT_SAMPLE


def main():
    # Check backend URL
    backend_url = os.environ.get('MODEL_BACKEND_URL', '')
    if not backend_url:
        sys.stderr.write("ERROR: MODEL_BACKEND_URL environment variable not set.\n")
        sys.stderr.write("Set it to a working backend URL, e.g.:\n")
        sys.stderr.write("  export MODEL_BACKEND_URL=http://192.168.68.61:8001/generate\n")
        sys.exit(1)

    source_text = get_input_text()

    # Create translation input
    input = TranslationInput(
        segment_id='review_mode',
        source_text=source_text,
        glossary_terms=[]
    )

    try:
        # Draft translation
        draft_output = translate_draft(input)
        # Polish translation
        polished_output = polish_translation(input, draft_output)
        # Print only the polished translation text
        print(polished_output.polished_translation)
    except Exception as e:
        # Print error to stderr and exit with non-zero code
        sys.stderr.write(f"Translation failed: {e}\n")
        sys.exit(1)


if __name__ == '__main__':
    main()