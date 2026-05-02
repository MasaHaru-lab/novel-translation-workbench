#!/usr/bin/env python3
"""
Add OpenAI format tests to test_backend_adapter.py
"""
import sys

test_file = "app/tests/test_backend_adapter.py"

with open(test_file, 'r') as f:
    lines = f.readlines()

# Find line number of test_success_with_content_field
insert_idx = None
for i, line in enumerate(lines):
    if "def test_success_with_content_field" in line:
        # Find the end of this test method (next method definition)
        for j in range(i + 1, len(lines)):
            if lines[j].strip().startswith("def test_") or lines[j].strip().startswith("@patch"):
                # Actually we need to insert after the blank line before the next test
                # Look backwards for blank line
                for k in range(j - 1, i, -1):
                    if lines[k].strip() == "":
                        insert_idx = k + 1  # insert after blank line
                        break
                break
        if insert_idx is not None:
            break

if insert_idx is None:
    print("Could not find insertion point")
    sys.exit(1)

# New test methods
new_tests = '''    @patch('app.translate.backend_adapter.requests.post')
    def test_success_with_openai_message_content(self, mock_post):
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "choices": [
                {
                    "message": {
                        "content": "OpenAI translated text."
                    }
                }
            ]
        }
        mock_post.return_value = mock_response

        config.MODEL_BACKEND_URL = "http://localhost:11434/api/generate"
        result = call_model_backend("Prompt")
        assert result == "OpenAI translated text."

    @patch('app.translate.backend_adapter.requests.post')
    def test_success_with_openai_choice_text(self, mock_post):
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "choices": [
                {
                    "text": "Choice text."
                }
            ]
        }
        mock_post.return_value = mock_response

        config.MODEL_BACKEND_URL = "http://localhost:11434/api/generate"
        result = call_model_backend("Prompt")
        assert result == "Choice text."

    @patch('app.translate.backend_adapter.requests.post')
    def test_success_with_openai_choice_content(self, mock_post):
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "choices": [
                {
                    "content": "Choice content."
                }
            ]
        }
        mock_post.return_value = mock_response

        config.MODEL_BACKEND_URL = "http://localhost:11434/api/generate"
        result = call_model_backend("Prompt")
        assert result == "Choice content."
'''

# Insert new tests
lines.insert(insert_idx, new_tests + '\n')

with open(test_file, 'w') as f:
    f.writelines(lines)

print(f"Inserted new tests at line {insert_idx}")