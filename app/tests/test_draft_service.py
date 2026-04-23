"""
Tests for the draft translation HTTP service.
"""
import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..'))

from unittest.mock import patch, MagicMock
import pytest

# Try to import FastAPI and related modules; skip all tests if not available
try:
    from fastapi.testclient import TestClient
    from app.service.draft_service import app
    from app.translate.schema import GlossaryTerm, TranslationInput, TranslationOutput
    from app.chapter.models import ChapterResult
    from app.chapter.manifest import ChapterStatus
    from app.config import config
    FASTAPI_AVAILABLE = True
except ImportError:
    FASTAPI_AVAILABLE = False

if not FASTAPI_AVAILABLE:
    pytest.skip("FastAPI not installed", allow_module_level=True)


client = TestClient(app)


@patch('app.service.draft_service.translate_draft_with_backend')
def test_translate_draft_endpoint_basic(mock_translate):
    """Test the /translate/draft endpoint with minimal input."""
    mock_translate.return_value = TranslationOutput(
        segment_id="test_1",
        draft_translation="Translated draft.",
        polished_translation="",
        notes=[]
    )
    payload = {
        "segment_id": "test_1",
        "source_text": "Hello world",
        "prev_context": None,
        "next_context": None,
        "glossary_terms": []
    }
    response = client.post("/translate/draft", json=payload)
    assert response.status_code == 200
    data = response.json()
    assert data["segment_id"] == "test_1"
    assert data["draft_translation"] == "Translated draft."
    assert data["polished_translation"] == ""
    assert data["notes"] == []
    # Verify adapter was called with correct input
    mock_translate.assert_called_once()
    call_arg = mock_translate.call_args[0][0]
    assert isinstance(call_arg, TranslationInput)
    assert call_arg.segment_id == "test_1"
    assert call_arg.source_text == "Hello world"


@patch('app.service.draft_service.translate_draft_with_backend')
def test_translate_draft_endpoint_with_glossary(mock_translate):
    """Test glossary replacement works through the endpoint."""
    mock_translate.return_value = TranslationOutput(
        segment_id="test_2",
        draft_translation="Young Lady called Prince",
        polished_translation="",
        notes=[]
    )
    payload = {
        "segment_id": "test_2",
        "source_text": "大小姐 called 王爷",
        "prev_context": "Previous segment.",
        "next_context": "Next segment.",
        "glossary_terms": [
            {"zh": "大小姐", "en": "Young Lady"},
            {"zh": "王爷", "en": "Prince"}
        ]
    }
    response = client.post("/translate/draft", json=payload)
    assert response.status_code == 200
    data = response.json()
    assert "Young Lady" in data["draft_translation"]
    assert "Prince" in data["draft_translation"]
    # Ensure original Chinese terms are replaced (adapter should also apply glossary)
    assert "大小姐" not in data["draft_translation"]
    assert "王爷" not in data["draft_translation"]
    # Verify adapter called with glossary terms
    mock_translate.assert_called_once()
    call_arg = mock_translate.call_args[0][0]
    assert len(call_arg.glossary_terms) == 2
    assert call_arg.glossary_terms[0].zh == "大小姐"
    assert call_arg.glossary_terms[0].en == "Young Lady"


@patch('app.service.draft_service.translate_draft_with_backend')
def test_translate_draft_endpoint_backend_error(mock_translate):
    """Test endpoint returns 503 when backend raises RuntimeError."""
    mock_translate.side_effect = RuntimeError("Backend down")
    payload = {
        "segment_id": "test_3",
        "source_text": "Hello",
        "glossary_terms": []
    }
    response = client.post("/translate/draft", json=payload)
    assert response.status_code == 503
    data = response.json()
    assert "detail" in data
    assert "Model backend error" in data["detail"]


@patch('app.service.draft_service.config')
def test_translate_draft_endpoint_missing_backend_url(mock_config):
    """Test endpoint returns 503 when MODEL_BACKEND_URL is empty."""
    mock_config.MODEL_BACKEND_URL = ""
    payload = {
        "segment_id": "test_4",
        "source_text": "Hello",
        "glossary_terms": []
    }
    response = client.post("/translate/draft", json=payload)
    assert response.status_code == 503
    data = response.json()
    assert "detail" in data
    assert "Model backend not configured" in data["detail"]


def test_translate_draft_endpoint_missing_field():
    """Test validation error when required field is missing."""
    payload = {
        # missing segment_id
        "source_text": "Hello",
        "glossary_terms": []
    }
    response = client.post("/translate/draft", json=payload)
    assert response.status_code == 422  # validation error


def test_health_endpoint():
    """Test the health check endpoint."""
    response = client.get("/health")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "healthy"


@patch('app.service.draft_service.ChapterOrchestrator')
def test_translate_chapter_endpoint_basic(mock_orchestrator_class):
    """Test the /translate/chapter endpoint with minimal input."""
    # Mock orchestrator instance and its run_with_manifest method
    mock_orchestrator = MagicMock()
    mock_orchestrator_class.return_value = mock_orchestrator

    # Create a mock ChapterResult with expected fields
    mock_result = ChapterResult(
        chapter_title="Test Chapter",
        source_text="测试章节内容",
        aggregated_translation="# Test Chapter\n\nTranslated content.",
        corrected_translation=None,
        chapter_status=ChapterStatus.COMPLETED,
        consistency_audit=None,
        correction_summary=None,
        strategy_plan_summary={"complexity_level": "low"},
        enactment={"consistent": True},
        segment_count=1,
        success_count=1,
        failed_segment_ids=[],
        resumable=False,
    )
    mock_orchestrator.run_with_manifest.return_value = mock_result

    payload = {
        "source_text": "测试章节内容"
    }
    response = client.post("/translate/chapter", json=payload)
    assert response.status_code == 200
    data = response.json()

    # Verify response structure
    assert data["chapter_title"] == "Test Chapter"
    assert data["aggregated_translation"] == "# Test Chapter\n\nTranslated content."
    assert data["corrected_translation"] is None
    assert data["chapter_status"] == "COMPLETED"
    assert data["consistency_audit"] is None
    assert data["correction_summary"] is None
    assert data["strategy_plan_summary"] == {"complexity_level": "low"}
    assert data["enactment"] == {"consistent": True}
    assert data["segment_count"] == 1
    assert data["success_count"] == 1
    assert data["failed_segment_ids"] == []
    assert data["resumable"] is False

    # Verify orchestrator was called correctly
    mock_orchestrator_class.assert_called_once()
    mock_orchestrator.run_with_manifest.assert_called_once_with(source_text="测试章节内容")


def test_translate_chapter_endpoint_empty_source():
    """Test /translate/chapter returns 400 when source_text is empty."""
    payload = {
        "source_text": "   "
    }
    response = client.post("/translate/chapter", json=payload)
    assert response.status_code == 400
    data = response.json()
    assert "detail" in data
    assert "source_text cannot be empty" in data["detail"]


if __name__ == "__main__":
    # Run tests with patches manually
    with patch('app.service.draft_service.translate_draft_with_backend'):
        test_translate_draft_endpoint_basic()
    with patch('app.service.draft_service.translate_draft_with_backend'):
        test_translate_draft_endpoint_with_glossary()
    test_translate_draft_endpoint_missing_field()
    test_health_endpoint()
    with patch('app.service.draft_service.ChapterOrchestrator'):
        test_translate_chapter_endpoint_basic()
    test_translate_chapter_endpoint_empty_source()
    print("All draft service tests passed.")