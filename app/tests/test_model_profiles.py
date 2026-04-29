"""Tests for the model profile system.

Covers:
- Profile dataclass and registry
- Profile resolution (known and unknown names)
- Prompt-HTTP adapter contract preservation
- DeepSeek/OpenAI-compatible adapter chat-completion contract
- Missing secret handling
- No-silent-fallback between providers
- No secret leakage in output metadata
- Config loader (.env.local parsing)
"""
import os
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..'))

from unittest.mock import patch, MagicMock
import pytest

from app.translate.model_profiles import (
    ModelProfile,
    get_profile,
    list_profiles,
    resolve_base_url,
    resolve_api_key,
    LOCAL_QWEN,
    DEEPSEEK_V4_FLASH,
    DEEPSEEK_V4_PRO,
)
from app.translate.backend_adapter import (
    call_model_backend,
    translate_draft_with_backend,
    translate_draft_with_profile,
)
from app.translate.schema import TranslationInput, TranslationOutput


# ============================================================================
# Profile registry
# ============================================================================


class TestProfileRegistry:
    """ModelProfile dataclass and registry behavior."""

    def test_builtin_profiles_exist(self):
        assert LOCAL_QWEN.name == "local-qwen"
        assert DEEPSEEK_V4_FLASH.name == "deepseek-v4-flash"
        assert DEEPSEEK_V4_PRO.name == "deepseek-v4-pro"

    def test_local_qwen_is_prompt_http(self):
        assert LOCAL_QWEN.provider == "prompt-http"
        assert LOCAL_QWEN.api_key_env is None  # no auth needed

    def test_deepseek_profiles_are_openai_compat(self):
        assert DEEPSEEK_V4_FLASH.provider == "openai-compat"
        assert DEEPSEEK_V4_PRO.provider == "openai-compat"
        assert DEEPSEEK_V4_FLASH.api_key_env == "DEEPSEEK_API_KEY"
        assert DEEPSEEK_V4_PRO.api_key_env == "DEEPSEEK_API_KEY"

    def test_get_profile_known(self):
        p = get_profile("local-qwen")
        assert p is LOCAL_QWEN

    def test_get_profile_unknown(self):
        with pytest.raises(KeyError, match="Unknown model profile"):
            get_profile("nonexistent")

    def test_list_profiles_returns_copy(self):
        profiles = list_profiles()
        assert "local-qwen" in profiles
        assert "deepseek-v4-flash" in profiles
        assert "deepseek-v4-pro" in profiles
        # Verify it's a copy
        profiles["bogus"] = object()
        assert "bogus" not in list_profiles()

    def test_profile_is_frozen(self):
        with pytest.raises(AttributeError):
            LOCAL_QWEN.name = "changed"

    def test_resolve_base_url_from_env(self):
        with patch.dict(os.environ, {"MODEL_BACKEND_URL": "http://test:1234/api"}, clear=True):
            url = resolve_base_url(LOCAL_QWEN)
            assert url == "http://test:1234/api"

    def test_resolve_base_url_missing(self):
        with patch.dict(os.environ, {}, clear=True):
            with pytest.raises(RuntimeError, match="requires MODEL_BACKEND_URL"):
                resolve_base_url(LOCAL_QWEN)

    def test_resolve_api_key_returns_none_when_not_needed(self):
        key = resolve_api_key(LOCAL_QWEN)
        assert key is None

    def test_resolve_api_key_from_env(self):
        with patch.dict(os.environ, {"DEEPSEEK_API_KEY": "sk-test123"}, clear=True):
            key = resolve_api_key(DEEPSEEK_V4_FLASH)
            assert key == "sk-test123"

    def test_resolve_api_key_missing(self):
        with patch.dict(os.environ, {}, clear=True):
            with pytest.raises(RuntimeError, match="requires DEEPSEEK_API_KEY"):
                resolve_api_key(DEEPSEEK_V4_FLASH)

    def test_deepseek_profiles_have_default_model(self):
        assert DEEPSEEK_V4_FLASH.default_model == "deepseek-chat"
        assert DEEPSEEK_V4_PRO.default_model == "deepseek-reasoner"
        assert LOCAL_QWEN.default_model is None


# ============================================================================
# Prompt-HTTP adapter preserves existing contract
# ============================================================================


class TestPromptHttpProfile:
    """When using a prompt-http profile, the request contract must match the
    existing ``call_model_backend`` behavior."""

    INPUT = TranslationInput(
        segment_id="p1",
        source_text="Hello world",
        glossary_terms=[],
    )

    @patch("app.translate.backend_adapter.call_model_backend")
    def test_contract_match(self, mock_call):
        mock_call.return_value = "Translated text."
        with patch.dict(os.environ, {"MODEL_BACKEND_URL": "http://localhost:11434/api/generate"}, clear=True):
            output = translate_draft_with_profile(self.INPUT, LOCAL_QWEN)
        assert output.draft_translation == "Translated text."
        # Verify the prompt-HTTP path calls call_model_backend
        assert mock_call.called

    @patch("app.translate.backend_adapter.call_model_backend")
    def test_metadata_in_notes(self, mock_call):
        mock_call.return_value = "Translated text."
        with patch.dict(os.environ, {"MODEL_BACKEND_URL": "http://localhost:11434/api/generate"}, clear=True):
            output = translate_draft_with_profile(self.INPUT, LOCAL_QWEN)
        # Notes must contain profile name, not raw URL or API key
        notes_str = "; ".join(output.notes)
        assert "Profile: local-qwen" in notes_str
        assert "Provider: prompt-http" in notes_str
        assert "http://localhost:11434" not in notes_str  # No raw URL

    @patch("app.translate.backend_adapter.call_model_backend")
    def test_prompt_http_backward_compat(self, mock_call):
        """The existing call_model_backend path (no profile) must still work."""
        mock_call.return_value = "Backward compat text."
        original_url = os.environ.get("MODEL_BACKEND_URL")
        os.environ["MODEL_BACKEND_URL"] = "http://localhost:11434/api/generate"
        try:
            output = translate_draft_with_backend(self.INPUT)
        finally:
            if original_url is None:
                del os.environ["MODEL_BACKEND_URL"]
            else:
                os.environ["MODEL_BACKEND_URL"] = original_url
        assert output.draft_translation == "Backward compat text."


# ============================================================================
# DeepSeek/OpenAI-compatible adapter
# ============================================================================


class TestDeepSeekProfile:
    """DeepSeek/openai-compat profiles build chat/completions style requests."""

    INPUT = TranslationInput(
        segment_id="d1",
        source_text="Translate this",
        glossary_terms=[],
    )

    @patch("app.translate.deepseek_adapter.requests.post")
    def test_chat_completion_request_structure(self, mock_post):
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "choices": [{"message": {"content": "DeepSeek response."}}]
        }
        mock_post.return_value = mock_response

        with patch.dict(os.environ, {
            "DEEPSEEK_BASE_URL": "https://api.deepseek.com/v1",
            "DEEPSEEK_API_KEY": "sk-test123",
        }, clear=True):
            output = translate_draft_with_profile(self.INPUT, DEEPSEEK_V4_FLASH)

        assert output.draft_translation == "DeepSeek response."

        # Verify the request was chat/completions style
        call_kwargs = mock_post.call_args
        assert call_kwargs is not None
        url = call_kwargs[0][0]
        body = call_kwargs[1]["json"]
        headers = call_kwargs[1]["headers"]

        assert "/chat/completions" in url
        assert body["model"] == "deepseek-chat"
        assert len(body["messages"]) == 1
        assert body["messages"][0]["role"] == "user"
        assert "Translate this" in body["messages"][0]["content"]
        assert headers["Authorization"] == "Bearer sk-test123"

    @patch("app.translate.deepseek_adapter.requests.post")
    def test_metadata_in_notes(self, mock_post):
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "choices": [{"message": {"content": "DeepSeek response."}}]
        }
        mock_post.return_value = mock_response

        with patch.dict(os.environ, {
            "DEEPSEEK_BASE_URL": "https://api.deepseek.com/v1",
            "DEEPSEEK_API_KEY": "sk-test123",
        }, clear=True):
            output = translate_draft_with_profile(self.INPUT, DEEPSEEK_V4_FLASH)

        notes_str = "; ".join(output.notes)
        assert "Profile: deepseek-v4-flash" in notes_str
        assert "Provider: openai-compat" in notes_str
        assert "Model: deepseek-chat" in notes_str
        # No secrets in notes
        assert "sk-test123" not in notes_str
        assert "DEEPSEEK_API_KEY" not in notes_str
        assert "https://api.deepseek.com" not in notes_str

    @patch("app.translate.deepseek_adapter.requests.post")
    def test_deepseek_v4_pro_default_model(self, mock_post):
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "choices": [{"message": {"content": "Pro response."}}]
        }
        mock_post.return_value = mock_response

        with patch.dict(os.environ, {
            "DEEPSEEK_BASE_URL": "https://api.deepseek.com/v1",
            "DEEPSEEK_API_KEY": "sk-test123",
        }, clear=True):
            output = translate_draft_with_profile(self.INPUT, DEEPSEEK_V4_PRO)

        assert output.draft_translation == "Pro response."
        body = mock_post.call_args[1]["json"]
        assert body["model"] == "deepseek-reasoner"

    @patch("app.translate.deepseek_adapter.requests.post")
    def test_deepseek_failure_no_silent_fallback(self, mock_post):
        """DeepSeek failure must propagate — no silent fallback to local."""
        mock_post.side_effect = RuntimeError("API unavailable")

        with patch.dict(os.environ, {
            "DEEPSEEK_BASE_URL": "https://api.deepseek.com/v1",
            "DEEPSEEK_API_KEY": "sk-test123",
        }, clear=True):
            with pytest.raises(RuntimeError, match="API unavailable"):
                translate_draft_with_profile(self.INPUT, DEEPSEEK_V4_FLASH)

    def test_deepseek_missing_api_key(self):
        """Missing API key produces a clear error, no magic fallback."""
        with patch.dict(os.environ, {
            "DEEPSEEK_BASE_URL": "https://api.deepseek.com/v1",
        }, clear=True):
            with pytest.raises(RuntimeError, match="requires DEEPSEEK_API_KEY"):
                translate_draft_with_profile(self.INPUT, DEEPSEEK_V4_FLASH)

    def test_deepseek_missing_base_url(self):
        """Missing base URL produces a clear error."""
        with patch.dict(os.environ, {
            "DEEPSEEK_API_KEY": "sk-test123",
        }, clear=True):
            with pytest.raises(RuntimeError, match="requires DEEPSEEK_BASE_URL"):
                translate_draft_with_profile(self.INPUT, DEEPSEEK_V4_FLASH)


# ============================================================================
# No-silent-fallback guarantee
# ============================================================================


class TestNoSilentFallback:
    """A provider failure must not silently switch to another provider."""

    INPUT = TranslationInput(
        segment_id="f1",
        source_text="Test",
        glossary_terms=[],
    )

    @patch("app.translate.deepseek_adapter.requests.post")
    def test_deepseek_timeout_no_fallback(self, mock_post):
        """DeepSeek timeout → error, not a silent switch to local."""
        from requests.exceptions import Timeout

        mock_post.side_effect = Timeout("Connection timed out")

        with patch.dict(os.environ, {
            "DEEPSEEK_BASE_URL": "https://api.deepseek.com/v1",
            "DEEPSEEK_API_KEY": "sk-test123",
        }, clear=True):
            with pytest.raises(RuntimeError, match="timeout"):
                translate_draft_with_profile(self.INPUT, DEEPSEEK_V4_FLASH)

    @patch("app.translate.deepseek_adapter.requests.post")
    def test_deepseek_http_500_no_fallback(self, mock_post):
        """DeepSeek 500 → error, not a silent switch to local."""
        from requests.exceptions import HTTPError

        mock_response = MagicMock()
        mock_response.status_code = 500
        mock_response.raise_for_status.side_effect = HTTPError("500 Server Error")
        mock_post.return_value = mock_response

        with patch.dict(os.environ, {
            "DEEPSEEK_BASE_URL": "https://api.deepseek.com/v1",
            "DEEPSEEK_API_KEY": "sk-test123",
        }, clear=True):
            with pytest.raises(RuntimeError, match="request error|500"):
                translate_draft_with_profile(self.INPUT, DEEPSEEK_V4_FLASH)


# ============================================================================
# Secret leakage safety
# ============================================================================


class TestNoSecretLeakage:
    """Runtime outputs must not contain resolved secret values."""

    INPUT = TranslationInput(
        segment_id="s1",
        source_text="Secret test",
        glossary_terms=[],
    )

    @patch("app.translate.backend_adapter.call_model_backend")
    def test_prompt_http_notes_no_url(self, mock_call):
        """Prompt-HTTP profile notes must not contain raw backend URL."""
        mock_call.return_value = "Text."
        with patch.dict(os.environ, {"MODEL_BACKEND_URL": "http://secret-host:11434"}, clear=True):
            output = translate_draft_with_profile(self.INPUT, LOCAL_QWEN)
        notes = "; ".join(output.notes)
        assert "secret-host" not in notes
        assert "11434" not in notes
        assert "http://" not in notes

    @patch("app.translate.deepseek_adapter.requests.post")
    def test_deepseek_notes_no_secrets(self, mock_post):
        """DeepSeek notes must not contain API key or base URL."""
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "choices": [{"message": {"content": "Secret text."}}]
        }
        mock_post.return_value = mock_response

        with patch.dict(os.environ, {
            "DEEPSEEK_BASE_URL": "https://api.deepseek.com/v1",
            "DEEPSEEK_API_KEY": "sk-ultra-secret-key-value",
        }, clear=True):
            output = translate_draft_with_profile(self.INPUT, DEEPSEEK_V4_FLASH)
        notes = "; ".join(output.notes)
        assert "sk-ultra-secret-key-value" not in notes
        assert "api.deepseek.com" not in notes
        assert "DEEPSEEK_API_KEY" not in notes


# ============================================================================
# Config loader
# ============================================================================


class TestConfigLoader:
    """The .env.local loader must parse KEY=VALUE lines and set os.environ."""

    def test_load_env_local(self):
        from app.config_loader import load_env_local

        with tempfile.TemporaryDirectory() as tmpdir:
            env_file = Path(tmpdir) / ".env.local"
            env_file.write_text(
                "DEEPSEEK_API_KEY=sk-test-from-file\n"
                "MODEL_BACKEND_URL=http://localhost:9999\n"
                "# This is a comment\n"
                "\n"
                "EMPTY_LINE_ABOVE=\n"
            )
            with patch.dict(os.environ, {}, clear=True):
                load_env_local(project_root=tmpdir)
                assert os.environ["DEEPSEEK_API_KEY"] == "sk-test-from-file"
                assert os.environ["MODEL_BACKEND_URL"] == "http://localhost:9999"

    def test_load_env_local_missing_file(self):
        """Missing .env.local is not an error."""
        from app.config_loader import load_env_local

        with tempfile.TemporaryDirectory() as tmpdir:
            with patch.dict(os.environ, {}, clear=True):
                # Should not raise
                load_env_local(project_root=tmpdir)
                # No new variables should be set
                assert "DEEPSEEK_API_KEY" not in os.environ

    def test_env_var_takes_precedence(self):
        """Existing environment variables must not be overwritten by .env.local."""
        from app.config_loader import load_env_local

        with tempfile.TemporaryDirectory() as tmpdir:
            env_file = Path(tmpdir) / ".env.local"
            env_file.write_text("DEEPSEEK_API_KEY=sk-from-file\n")
            with patch.dict(os.environ, {"DEEPSEEK_API_KEY": "sk-from-env"}, clear=True):
                load_env_local(project_root=tmpdir)
                assert os.environ["DEEPSEEK_API_KEY"] == "sk-from-env"

    def test_idempotent(self):
        """Calling load_env_local multiple times is safe."""
        from app.config_loader import load_env_local

        # Reset internal flag
        import app.config_loader as cl
        cl._loaded = False

        with tempfile.TemporaryDirectory() as tmpdir:
            env_file = Path(tmpdir) / ".env.local"
            env_file.write_text("TEST_VAR=value1\n")
            with patch.dict(os.environ, {}, clear=True):
                load_env_local(project_root=tmpdir)
                assert os.environ["TEST_VAR"] == "value1"
                # Change file and call again
                env_file.write_text("TEST_VAR=value2\n")
                load_env_local(project_root=tmpdir)
                # Should still be value1 (idempotent)
                assert os.environ["TEST_VAR"] == "value1"
