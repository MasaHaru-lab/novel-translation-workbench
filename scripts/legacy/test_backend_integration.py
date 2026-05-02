#!/usr/bin/env python3
"""
Integration test of the model backend with actual translation.
"""
import os
import sys

os.environ["MODEL_BACKEND_URL"] = "http://192.168.68.61:8001/generate"
os.environ["MODEL_TIMEOUT_SECONDS"] = "30"

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from app.translate.schema import TranslationInput, GlossaryTerm
from app.translate.backend_adapter import translate_draft_with_backend

def main():
    print("Testing translation backend with Chinese input...")

    # Simple Chinese sentence
    input = TranslationInput(
        segment_id="test_1",
        source_text="今天天气很好。",
        glossary_terms=[]
    )

    try:
        output = translate_draft_with_backend(input)
        print(f"SUCCESS!")
        print(f"Segment ID: {output.segment_id}")
        print(f"Draft translation: {output.draft_translation}")
        print(f"Notes: {output.notes}")
        return 0
    except Exception as e:
        print(f"FAILED! Error: {e}")
        import traceback
        traceback.print_exc()
        return 1

if __name__ == "__main__":
    sys.exit(main())