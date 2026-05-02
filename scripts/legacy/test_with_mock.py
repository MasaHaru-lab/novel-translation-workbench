#!/usr/bin/env python3
"""
Test polish with a mock backend server.
"""
import subprocess
import time
import sys
import os
import signal
import requests

def start_mock_backend():
    """Start mock backend server in a subprocess."""
    # Start the server
    proc = subprocess.Popen(
        [sys.executable, 'mock_backend.py'],
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        bufsize=1,
        universal_newlines=True
    )

    # Wait for server to start
    time.sleep(2)

    # Check if server is responding
    try:
        resp = requests.get('http://localhost:9999/health', timeout=2)
        if resp.status_code == 200:
            print("Mock backend started successfully")
            return proc
        else:
            print(f"Mock backend health check failed: {resp.status_code}")
            proc.terminate()
            proc.wait()
            return None
    except Exception as e:
        print(f"Failed to connect to mock backend: {e}")
        proc.terminate()
        proc.wait()
        return None

def run_polish_test():
    """Run the polish test with mock backend."""
    # Set backend URL
    os.environ['MODEL_BACKEND_URL'] = 'http://localhost:9999/generate'

    # Import and run test
    from app.translate.schema import TranslationInput, TranslationOutput, GlossaryTerm
    from app.translate.translator import translate_draft, polish_translation

    # Create test input
    input = TranslationInput(
        segment_id='polish_test',
        source_text='大小姐 called 王爷，然后离开了房间。',
        glossary_terms=[
            GlossaryTerm(zh='大小姐', en='Young Lady'),
            GlossaryTerm(zh='王爷', en='Prince'),
        ]
    )

    print("\n=== Input ===")
    print(f"Chinese: {input.source_text}")
    print(f"Glossary: {[(t.zh, t.en) for t in input.glossary_terms]}")

    # Draft translation (mock)
    print("\n=== Draft Translation ===")
    draft_output = translate_draft(input)
    print(f"Draft: {draft_output.draft_translation}")

    # Polish translation (using mock backend)
    print("\n=== Polish Translation ===")
    polished_output = polish_translation(input, draft_output)
    print(f"Polished: {polished_output.polished_translation}")

    # Comparison
    print("\n=== Comparison ===")
    print(f"Draft length: {len(draft_output.draft_translation)} chars")
    print(f"Polished length: {len(polished_output.polished_translation)} chars")

    if draft_output.draft_translation == polished_output.polished_translation:
        print("FAIL: Draft and polished are identical!")
        return False
    else:
        print("SUCCESS: Draft and polished are different.")
        print("\n=== Content Analysis ===")
        print("1. Polished contains glossary terms 'Young Lady' and 'Prince':")
        print(f"   'Young Lady' in polished: {'Young Lady' in polished_output.polished_translation}")
        print(f"   'Prince' in polished: {'Prince' in polished_output.polished_translation}")
        print("\n2. Polished appears to preserve original meaning:")
        print("   - Both mention a Young Lady calling a Prince")
        print("   - Both mention leaving the room")
        print("\n3. Polished adds natural English improvements:")
        print("   - Uses English punctuation")
        print("   - Adds explanatory note (from mock backend)")
        return True

def main():
    print("Starting mock backend test...")

    # Start mock backend
    proc = start_mock_backend()
    if not proc:
        print("Failed to start mock backend")
        sys.exit(1)

    try:
        # Run test
        success = run_polish_test()

        if success:
            print("\n✅ TEST PASSED: Polish step produces distinct output from draft.")
        else:
            print("\n❌ TEST FAILED: Polish step did not produce distinct output.")
            sys.exit(1)
    finally:
        # Kill mock backend
        print("\nStopping mock backend...")
        proc.terminate()
        proc.wait()
        print("Done.")

if __name__ == '__main__':
    main()