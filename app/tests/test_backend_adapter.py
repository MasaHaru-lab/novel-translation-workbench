"""
Tests for the backend adapter that calls the model HTTP endpoint.
"""
import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..'))

from unittest.mock import patch, MagicMock
import pytest
import json
import requests.exceptions
from app.translate.schema import TranslationInput, GlossaryTerm
from app.translate.backend_adapter import (
    build_draft_prompt,
    call_model_backend,
    translate_draft_with_backend
)
from app.config import config


class TestBuildDraftPrompt:
    """Test prompt building."""

    def test_basic(self):
        input = TranslationInput(
            segment_id="1",
            source_text="Hello world",
            glossary_terms=[]
        )
        prompt = build_draft_prompt(input)
        # Prompt-file content from prompts/prompt_a.md (unified with translator path).
        assert "Prompt A" in prompt or "Literary Translation Draft" in prompt
        assert "Hello world" in prompt
        assert "Draft translation:" in prompt

    def test_with_glossary(self):
        input = TranslationInput(
            segment_id="2",
            source_text="大小姐 called 王爷",
            glossary_terms=[
                GlossaryTerm(zh="大小姐", en="Young Lady"),
                GlossaryTerm(zh="王爷", en="Prince")
            ]
        )
        prompt = build_draft_prompt(input)
        assert "大小姐 → Young Lady" in prompt
        assert "王爷 → Prince" in prompt
        assert "Glossary terms" in prompt

    def test_with_context(self):
        input = TranslationInput(
            segment_id="3",
            source_text="Main text.",
            prev_context="Previous segment.",
            next_context="Next segment.",
            glossary_terms=[]
        )
        prompt = build_draft_prompt(input)
        assert "Previous segment (for context only" in prompt
        assert "Next segment (for context only" in prompt
        assert "Previous segment." in prompt
        assert "Next segment." in prompt
        # Ensure context lines are not marked as translation target
        assert "Original Chinese text:" in prompt
        assert "Main text." in prompt


class TestCallModelBackend:
    """Test the HTTP call to model backend."""

    @patch('app.translate.backend_adapter.requests.post')
    def test_success_with_text_field(self, mock_post):
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"text": "Translated text."}
        mock_post.return_value = mock_response

        # Temporarily set config
        original_url = config.MODEL_BACKEND_URL
        config.MODEL_BACKEND_URL = "http://localhost:11434/api/generate"
        try:
            result = call_model_backend("Prompt")
            assert result == "Translated text."
        finally:
            config.MODEL_BACKEND_URL = original_url

        mock_post.assert_called_once_with(
            "http://localhost:11434/api/generate",
            json={"prompt": "Prompt"},
            timeout=config.MODEL_TIMEOUT_SECONDS
        )

    @patch('app.translate.backend_adapter.requests.post')
    def test_success_with_response_field(self, mock_post):
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"response": "Generated response."}
        mock_post.return_value = mock_response

        config.MODEL_BACKEND_URL = "http://localhost:11434/api/generate"
        result = call_model_backend("Prompt")
        assert result == "Generated response."

    @patch('app.translate.backend_adapter.requests.post')
    def test_success_with_generated_text_field(self, mock_post):
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"generated_text": "Generated."}
        mock_post.return_value = mock_response

        config.MODEL_BACKEND_URL = "http://localhost:11434/api/generate"
        result = call_model_backend("Prompt")
        assert result == "Generated."

    @patch('app.translate.backend_adapter.requests.post')
    def test_success_with_content_field(self, mock_post):
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"content": "Content."}
        mock_post.return_value = mock_response

        config.MODEL_BACKEND_URL = "http://localhost:11434/api/generate"
        result = call_model_backend("Prompt")
        assert result == "Content."

    @patch('app.translate.backend_adapter.requests.post')
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

    @patch('app.translate.backend_adapter.requests.post')
    def test_success_with_plain_string_response(self, mock_post):
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = "Just a string"
        mock_post.return_value = mock_response

        config.MODEL_BACKEND_URL = "http://localhost:11434/api/generate"
        result = call_model_backend("Prompt")
        assert result == "Just a string"

    @patch('app.translate.backend_adapter.requests.post')
    def test_missing_url(self, mock_post):
        original_url = config.MODEL_BACKEND_URL
        config.MODEL_BACKEND_URL = ""
        try:
            with pytest.raises(RuntimeError, match="MODEL_BACKEND_URL not configured"):
                call_model_backend("Prompt")
        finally:
            config.MODEL_BACKEND_URL = original_url
        mock_post.assert_not_called()

    @patch('app.translate.backend_adapter.requests.post')
    def test_connection_error(self, mock_post):
        mock_post.side_effect = requests.exceptions.ConnectionError("Cannot connect")
        config.MODEL_BACKEND_URL = "http://localhost:11434/api/generate"
        with pytest.raises(RuntimeError, match="Model backend connection failed"):
            call_model_backend("Prompt")

    @patch('app.translate.backend_adapter.requests.post')
    def test_timeout(self, mock_post):
        mock_post.side_effect = requests.exceptions.Timeout("Timeout")
        config.MODEL_BACKEND_URL = "http://localhost:11434/api/generate"
        with pytest.raises(RuntimeError, match="Model backend timeout"):
            call_model_backend("Prompt")

    @patch('app.translate.backend_adapter.requests.post')
    def test_http_error(self, mock_post):
        mock_response = MagicMock()
        mock_response.status_code = 500
        mock_response.raise_for_status.side_effect = requests.exceptions.HTTPError("Server error")
        mock_post.return_value = mock_response
        config.MODEL_BACKEND_URL = "http://localhost:11434/api/generate"
        with pytest.raises(RuntimeError, match="Model backend request error"):
            call_model_backend("Prompt")

    @patch('app.translate.backend_adapter.requests.post')
    def test_invalid_json_response(self, mock_post):
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.side_effect = json.JSONDecodeError("Expecting value", "Not JSON", 0)
        mock_response.text = "Not JSON"
        mock_post.return_value = mock_response
        config.MODEL_BACKEND_URL = "http://localhost:11434/api/generate"
        with pytest.raises(RuntimeError, match="Model backend returned invalid JSON"):
            call_model_backend("Prompt")

    @patch('app.translate.backend_adapter.requests.post')
    def test_missing_text_field(self, mock_post):
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"unknown": "data"}
        mock_post.return_value = mock_response
        config.MODEL_BACKEND_URL = "http://localhost:11434/api/generate"
        with pytest.raises(RuntimeError, match="Model backend response missing text field"):
            call_model_backend("Prompt")


class TestTranslateDraftWithBackend:
    """Test the full adapter function."""

    @patch('app.translate.backend_adapter.call_model_backend')
    def test_success(self, mock_call):
        mock_call.return_value = "Translated draft with glossary."
        input = TranslationInput(
            segment_id="5",
            source_text="大小姐 called 王爷",
            glossary_terms=[
                GlossaryTerm(zh="大小姐", en="Young Lady"),
                GlossaryTerm(zh="王爷", en="Prince")
            ]
        )
        output = translate_draft_with_backend(input)
        assert output.segment_id == "5"
        assert output.draft_translation == "Translated draft with glossary."
        assert output.polished_translation == ""
        assert "Backend:" in output.notes[0]
        # Ensure glossary replacement was applied (though prompt already includes glossary)
        # The mock call returns text without replacement, but adapter applies again.
        # We'll verify that call_model_backend was called with a prompt containing glossary.
        prompt = mock_call.call_args[0][0]
        assert "大小姐 → Young Lady" in prompt

    @patch('app.translate.backend_adapter.call_model_backend')
    def test_glossary_replacement_safety(self, mock_call):
        # Simulate backend returning Chinese terms (should be replaced)
        mock_call.return_value = "大小姐 called 王爷"
        input = TranslationInput(
            segment_id="6",
            source_text="大小姐 called 王爷",
            glossary_terms=[
                GlossaryTerm(zh="大小姐", en="Young Lady"),
                GlossaryTerm(zh="王爷", en="Prince")
            ]
        )
        output = translate_draft_with_backend(input)
        # Expect glossary replacement applied after backend call
        assert "Young Lady" in output.draft_translation
        assert "Prince" in output.draft_translation
        assert "大小姐" not in output.draft_translation
        assert "王爷" not in output.draft_translation

    @patch('app.translate.backend_adapter.call_model_backend')
    def test_backend_error_propagates(self, mock_call):
        mock_call.side_effect = RuntimeError("Backend down")
        input = TranslationInput(
            segment_id="7",
            source_text="test",
            glossary_terms=[]
        )
        with pytest.raises(RuntimeError, match="Backend down"):
            translate_draft_with_backend(input)


class TestUnifiedPromptAssetPath:
    """Prove the backend/service draft path uses the same prompt/asset model
    as the local pipeline path.

    Together these tests show:
      - translate_draft_with_backend default behavior is unchanged for
        callers that don't pass assets_mode (still "full")
      - the prompt sent to call_model_backend now includes prompt_a.md
        content (not a local hardcoded prompt)
      - the project-assets block is injected by default
      - assets_mode="none" threaded internally suppresses asset injection
        on the backend/service path too
      - the HTTP endpoint surface (/translate/draft) is unchanged — it
        forwards without exposing a new parameter
    """

    ASSETS_HEADER = "Project memory (authoritative reference"

    def _input(self) -> TranslationInput:
        return TranslationInput(
            segment_id="svc-1",
            source_text="大小姐 called 王爷",
            prev_context="前文。",
            next_context="后文。",
            glossary_terms=[GlossaryTerm(zh="大小姐", en="Young Lady")],
        )

    @patch('app.translate.backend_adapter.call_model_backend')
    def test_default_prompt_carries_prompt_file_content(self, mock_call):
        mock_call.return_value = "draft"
        translate_draft_with_backend(self._input())
        prompt = mock_call.call_args[0][0]
        # Content sourced from prompts/prompt_a.md (not the old hardcoded text).
        assert "Prompt A" in prompt or "Literary Translation Draft" in prompt
        assert "Original Chinese text:" in prompt
        assert "Draft translation:" in prompt

    @patch('app.translate.backend_adapter.call_model_backend')
    def test_default_prompt_carries_project_assets(self, mock_call):
        # Only meaningful if any asset file exists on disk in this project.
        from app.translate.translator import build_project_assets_block
        if not build_project_assets_block("full"):
            pytest.skip("No project assets on disk to assert against")
        mock_call.return_value = "draft"
        translate_draft_with_backend(self._input())
        prompt = mock_call.call_args[0][0]
        assert self.ASSETS_HEADER in prompt

    @patch('app.translate.backend_adapter.call_model_backend')
    def test_assets_mode_none_suppresses_asset_injection(self, mock_call):
        mock_call.return_value = "draft"
        translate_draft_with_backend(self._input(), assets_mode="none")
        prompt = mock_call.call_args[0][0]
        assert self.ASSETS_HEADER not in prompt
        # Non-asset content still present — only the assets block is removed.
        assert "Original Chinese text:" in prompt
        assert "大小姐 → Young Lady" in prompt

    @patch('app.translate.backend_adapter.call_model_backend')
    def test_full_vs_none_prompts_differ(self, mock_call):
        from app.translate.translator import build_project_assets_block
        if not build_project_assets_block("full"):
            pytest.skip("No project assets on disk to differentiate modes")
        mock_call.return_value = "draft"
        translate_draft_with_backend(self._input(), assets_mode="full")
        full_prompt = mock_call.call_args[0][0]
        translate_draft_with_backend(self._input(), assets_mode="none")
        none_prompt = mock_call.call_args[0][0]
        assert full_prompt != none_prompt
        assert self.ASSETS_HEADER in full_prompt
        assert self.ASSETS_HEADER not in none_prompt

    @patch('app.translate.backend_adapter.call_model_backend')
    def test_invalid_assets_mode_rejected(self, mock_call):
        mock_call.return_value = "draft"
        with pytest.raises(ValueError):
            translate_draft_with_backend(self._input(), assets_mode="bogus")

    @patch('app.translate.backend_adapter.call_model_backend')
    def test_backend_path_matches_translator_path(self, mock_call):
        """The prompt the service path sends to call_model_backend is
        byte-identical to the prompt the local pipeline path sends, given
        the same input and assets_mode. Proves the two paths are unified
        at the prompt level."""
        from app.translate.translator import (
            translate_draft,
            build_project_assets_block,
        )
        mock_call.return_value = "draft"

        # Local pipeline path.
        os_backup = os.environ.get('MODEL_BACKEND_URL')
        os.environ['MODEL_BACKEND_URL'] = 'http://unified-test.example/api'
        try:
            translate_draft(self._input(), assets_mode="full")
            local_prompt = mock_call.call_args[0][0]

            # Backend/service path.
            translate_draft_with_backend(self._input(), assets_mode="full")
            service_prompt = mock_call.call_args[0][0]
        finally:
            if os_backup is None:
                os.environ.pop('MODEL_BACKEND_URL', None)
            else:
                os.environ['MODEL_BACKEND_URL'] = os_backup

        assert local_prompt == service_prompt


class TestServiceEndpointUnchanged:
    """The HTTP endpoint should not have grown a public assets_mode parameter
    in this batch — default behavior is unchanged and the request shape is
    identical to before."""

    def test_no_assets_mode_on_request_model(self):
        from app.service.draft_service import TranslationInputModel
        # The request model must not have an assets_mode field (no new public surface).
        assert "assets_mode" not in TranslationInputModel.model_fields

    def test_endpoint_still_accepts_legacy_payload(self):
        from fastapi.testclient import TestClient
        from app.service.draft_service import app
        from app.translate.schema import TranslationOutput

        client = TestClient(app)
        with patch(
            'app.service.draft_service.translate_draft_with_backend'
        ) as mock_translate:
            mock_translate.return_value = TranslationOutput(
                segment_id="e1",
                draft_translation="ok",
                polished_translation="",
                notes=[],
            )
            payload = {
                "segment_id": "e1",
                "source_text": "hi",
                "glossary_terms": [],
            }
            response = client.post("/translate/draft", json=payload)
        assert response.status_code == 200
        # translate_draft_with_backend must still be callable with a single
        # positional argument (no required assets_mode) — preserves the
        # existing service contract.
        call_kwargs = mock_translate.call_args.kwargs
        assert "assets_mode" not in call_kwargs


if __name__ == "__main__":
    pytest.main([__file__, "-v"])