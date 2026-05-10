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
    from app.chapter.manifest import ChapterStatus, SegmentStatus
    from app.config import config
    FASTAPI_AVAILABLE = True
except ImportError:
    FASTAPI_AVAILABLE = False

if not FASTAPI_AVAILABLE:
    pytest.skip("FastAPI not installed", allow_module_level=True)


client = TestClient(app)


@patch('app.service.draft_service.config')
@patch('app.service.draft_service.translate_draft_with_backend')
def test_translate_draft_endpoint_basic(mock_translate, mock_config):
    """Test the /translate/draft endpoint with minimal input."""
    mock_config.MODEL_BACKEND_URL = "http://mock-backend"
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


@patch('app.service.draft_service.config')
@patch('app.service.draft_service.translate_draft_with_backend')
def test_translate_draft_endpoint_with_glossary(mock_translate, mock_config):
    """Test glossary replacement works through the endpoint."""
    mock_config.MODEL_BACKEND_URL = "http://mock-backend"
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


@patch('app.service.draft_service.config')
@patch('app.service.draft_service.translate_draft_with_backend')
def test_translate_draft_endpoint_backend_error(mock_translate, mock_config):
    """Test endpoint returns 503 when backend raises RuntimeError."""
    mock_config.MODEL_BACKEND_URL = "http://mock-backend"
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


@patch.dict(os.environ, {"CHAPTER_API_MODE": "smoke"})
@patch('app.translate.backend_adapter.call_model_backend')
def test_api_chapters_product_endpoint_smoke_no_backend_call(mock_backend_call):
    """Product endpoint returns smoke output when CHAPTER_API_MODE=smoke."""
    mock_backend_call.side_effect = AssertionError("backend should not be called")
    original_backend_url = config.MODEL_BACKEND_URL
    config.MODEL_BACKEND_URL = "http://real-backend.invalid"
    try:
        response = client.post("/api/chapters", json={
            "title": "Display Title",
            "source_text": "第一章\n\n测试内容",
        })
    finally:
        config.MODEL_BACKEND_URL = original_backend_url

    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "completed"
    assert data["title"] == "Display Title"
    assert "[SMOKE TEST" in data["final_text"]
    assert data["segments"]
    assert data["error"] is None
    mock_backend_call.assert_not_called()


@patch.dict(os.environ, {"CHAPTER_API_MODE": "real"})
@patch('app.translate.model_profiles.get_profile')
@patch('app.config_loader.load_env_local')
@patch('app.service.draft_service.translate_draft_with_profile')
@patch('app.service.draft_service.ChapterOrchestrator')
def test_api_chapters_product_endpoint_real_mode_uses_deepseek_profile(
    mock_orchestrator_class,
    mock_translate_with_profile,
    mock_load_env,
    mock_get_profile,
):
    """Real product mode routes through the existing DeepSeek profile path."""
    mock_profile = MagicMock(name="deepseek-profile")
    mock_get_profile.return_value = mock_profile

    seg = TranslationOutput(
        segment_id="1",
        draft_translation="Draft",
        polished_translation="Real translated text.",
    )
    mock_result = ChapterResult(
        chapter_title="Real Mode",
        source_text="你好。",
        segment_results=[seg],
        aggregated_translation="Real translated text.",
        chapter_status=ChapterStatus.COMPLETED,
    )
    mock_orchestrator = MagicMock()
    mock_orchestrator.run_with_manifest.return_value = mock_result
    mock_orchestrator_class.return_value = mock_orchestrator

    response = client.post("/api/chapters", json={
        "title": "Real Mode",
        "source_text": "你好。",
    })

    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "completed"
    assert data["title"] == "Real Mode"
    assert data["final_text"] == "Real translated text."
    assert data["segments"] == [{"segment_id": "1", "final_text": "Real translated text."}]

    mock_load_env.assert_called_once()
    mock_get_profile.assert_called_once_with("deepseek-v4-flash")
    mock_orchestrator.run_with_manifest.assert_called_once()
    kwargs = mock_orchestrator.run_with_manifest.call_args.kwargs
    assert kwargs["source_text"] == "你好。"
    assert kwargs["smoke_test"] is False
    assert kwargs["model_profile"] is mock_profile
    assert callable(kwargs["translate_draft_fn"])

    inp = TranslationInput(segment_id="1", source_text="你好。")
    mock_translate_with_profile.return_value = seg
    assert kwargs["translate_draft_fn"](inp) is seg
    mock_translate_with_profile.assert_called_once_with(inp, mock_profile)


def test_api_chapters_product_endpoint_empty_source():
    """Product endpoint rejects empty source text."""
    response = client.post("/api/chapters", json={"source_text": "   "})
    assert response.status_code == 400
    assert "source_text cannot be empty" in response.json()["detail"]


def test_api_chapters_cors_allows_vercel_frontend():
    """CORS preflight allows the deployed Vercel frontend origin."""
    response = client.options(
        "/api/chapters",
        headers={
            "Origin": "https://novel-translation-workbench-ui.vercel.app",
            "Access-Control-Request-Method": "POST",
        },
    )
    assert response.status_code == 200
    assert (
        response.headers["access-control-allow-origin"]
        == "https://novel-translation-workbench-ui.vercel.app"
    )


def test_api_chapters_cors_allows_local_frontend_dev_origins():
    """CORS preflight allows local frontend development origins."""
    for origin in (
        "http://localhost:3000",
        "http://127.0.0.1:3000",
        "http://localhost:5173",
        "http://127.0.0.1:5173",
    ):
        response = client.options(
            "/api/chapters",
            headers={
                "Origin": origin,
                "Access-Control-Request-Method": "POST",
            },
        )
        assert response.status_code == 200
        assert response.headers["access-control-allow-origin"] == origin


@patch('app.service.draft_service.ChapterOrchestrator')
def test_translate_chapter_endpoint_basic(mock_orchestrator_class):
    """Test the /translate/chapter endpoint with minimal input."""
    # Mock orchestrator instance and its run_with_manifest method
    mock_orchestrator = MagicMock()
    mock_orchestrator_class.return_value = mock_orchestrator

    # Create a mock ChapterResult — segment_count and success_count are
    # properties computed from segment_results and segment_statuses.
    from app.translate.schema import TranslationOutput
    seg = TranslationOutput(segment_id="1", draft_translation="", polished_translation="# Test Chapter\n\nTranslated content.")
    mock_result = ChapterResult(
        chapter_title="Test Chapter",
        source_text="测试章节内容",
        segment_results=[seg],
        aggregated_translation="# Test Chapter\n\nTranslated content.",
        chapter_status=ChapterStatus.COMPLETED,
        segment_statuses={"1": SegmentStatus.COMPLETED},
        strategy_plan_summary={"complexity_level": "low"},
        enactment={"consistent": True},
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
    assert data["chapter_status"] == "completed"
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
    mock_orchestrator.run_with_manifest.assert_called_once()
    kwargs = mock_orchestrator.run_with_manifest.call_args.kwargs
    assert kwargs["source_text"] == "测试章节内容"
    assert kwargs.get("manifest_path") is None
    assert kwargs.get("existing_manifest") is None


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


@patch('app.service.draft_service.ChapterOrchestrator')
def test_translate_chapter_endpoint_internal_error(mock_orchestrator_class):
    """Orchestrator failure should return 500."""
    mock_orchestrator = MagicMock()
    mock_orchestrator_class.return_value = mock_orchestrator
    mock_orchestrator.run_with_manifest.side_effect = RuntimeError("Backend timeout")

    payload = {"source_text": "测试内容"}
    response = client.post("/translate/chapter", json=payload)
    assert response.status_code == 500
    data = response.json()
    assert "Internal server error" in data["detail"]


@patch('app.service.draft_service.ChapterOrchestrator')
def test_translate_chapter_endpoint_partial_result(mock_orchestrator_class):
    """Partial translation should be reflected in the response."""
    mock_orchestrator = MagicMock()
    mock_orchestrator_class.return_value = mock_orchestrator

    seg = TranslationOutput(segment_id="1", draft_translation="", polished_translation="Partial content.")
    mock_result = ChapterResult(
        chapter_title="Partial Chapter",
        source_text="source",
        segment_results=[seg],
        segment_statuses={"1": SegmentStatus.COMPLETED, "2": SegmentStatus.FAILED},
        aggregated_translation="# Partial\n\nPartial content.",
        chapter_status=ChapterStatus.PARTIAL,
        failed_segment_ids=["2"],
        resumable=True,
    )
    mock_orchestrator.run_with_manifest.return_value = mock_result

    payload = {"source_text": "source"}
    response = client.post("/translate/chapter", json=payload)
    assert response.status_code == 200
    data = response.json()
    assert data["chapter_status"] == "partial"
    assert data["segment_count"] == 1
    assert data["success_count"] == 1
    assert data["failed_segment_ids"] == ["2"]
    assert data["resumable"] is True


@patch('app.service.draft_service.ChapterOrchestrator')
def test_translate_chapter_endpoint_with_consistency_audit(mock_orchestrator_class):
    """Consistency audit/correction data should be returned when present."""
    mock_orchestrator = MagicMock()
    mock_orchestrator_class.return_value = mock_orchestrator

    seg = TranslationOutput(segment_id="1", draft_translation="", polished_translation="Content.")
    mock_result = ChapterResult(
        chapter_title="Test",
        source_text="source",
        segment_results=[seg],
        segment_statuses={"1": SegmentStatus.COMPLETED},
        aggregated_translation="Content.",
        chapter_status=ChapterStatus.COMPLETED,
        consistency_audit={
            "total_issues": 2,
            "auto_fixable": 1,
            "auto_fixed": 1,
            "by_category": {"term_inconsistency": 2},
        },
        correction_summary={
            "total_corrections": 1,
            "total_replacements": 2,
            "by_category": {"term_inconsistency": 1},
        },
        corrected_translation="Corrected content.",
    )
    mock_orchestrator.run_with_manifest.return_value = mock_result

    payload = {"source_text": "source"}
    response = client.post("/translate/chapter", json=payload)
    assert response.status_code == 200
    data = response.json()
    assert data["consistency_audit"]["total_issues"] == 2
    assert data["correction_summary"]["total_corrections"] == 1
    assert data["corrected_translation"] == "Corrected content."


# ── readable_summary field ────────────────────────────────────────────────


@patch('app.service.draft_service.ChapterOrchestrator')
def test_chapter_readable_summary_completed(mock_orchestrator_class):
    """readable_summary should show completed status with segment counts."""
    mock_orchestrator = MagicMock()
    mock_orchestrator_class.return_value = mock_orchestrator

    seg = TranslationOutput(segment_id="1", draft_translation="", polished_translation="# Test\n\nContent.")
    mock_result = ChapterResult(
        chapter_title="Test",
        source_text="source",
        segment_results=[seg],
        aggregated_translation="# Test\n\nContent.",
        chapter_status=ChapterStatus.COMPLETED,
        segment_statuses={"1": SegmentStatus.COMPLETED},
        failed_segment_ids=[],
        resumable=False,
    )
    mock_orchestrator.run_with_manifest.return_value = mock_result

    response = client.post("/translate/chapter", json={"source_text": "source"})
    assert response.status_code == 200
    data = response.json()

    summary = data["readable_summary"]
    assert "completed" in summary
    assert "1/1 segments completed" in summary
    assert "Failed:" not in summary
    assert "Remaining:" not in summary
    assert "Next step" not in summary


@patch('app.service.draft_service.ChapterOrchestrator')
def test_chapter_readable_summary_partial(mock_orchestrator_class):
    """Partial run should show failed segments, remaining count, and resume guidance."""
    mock_orchestrator = MagicMock()
    mock_orchestrator_class.return_value = mock_orchestrator
    mock_manifest = MagicMock()
    mock_manifest.manifest_path = "/tmp/test.manifest.json"
    mock_manifest.run_id = "partial_run"
    mock_manifest.segments = {}

    segs = [
        TranslationOutput(segment_id="1", draft_translation="", polished_translation="Seg 1"),
        TranslationOutput(segment_id="2", draft_translation="", polished_translation=""),
        TranslationOutput(segment_id="3", draft_translation="", polished_translation=""),
    ]
    mock_result = ChapterResult(
        chapter_title="Partial",
        source_text="source",
        segment_results=segs,
        aggregated_translation="Seg 1",
        chapter_status=ChapterStatus.PARTIAL,
        segment_statuses={"1": SegmentStatus.COMPLETED, "2": SegmentStatus.FAILED, "3": SegmentStatus.PENDING},
        failed_segment_ids=["2"],
        manifest=mock_manifest,
        resumable=True,
    )
    mock_orchestrator.run_with_manifest.return_value = mock_result

    response = client.post("/translate/chapter", json={"source_text": "source"})
    assert response.status_code == 200
    data = response.json()

    summary = data["readable_summary"]
    assert "partial" in summary
    assert "1/3 segments completed" in summary
    assert "2 segment(s) to complete" in summary
    assert "reuses 1 completed" in summary
    assert "processes 2 remaining" in summary
    assert "Manifest:" in summary
    assert "/tmp/test.manifest.json" in summary


@patch('app.service.draft_service.ChapterOrchestrator')
def test_chapter_readable_summary_all_failed(mock_orchestrator_class):
    """All-failed run should show failure count and retry guidance."""
    mock_orchestrator = MagicMock()
    mock_orchestrator_class.return_value = mock_orchestrator
    mock_manifest = MagicMock()
    mock_manifest.manifest_path = "/tmp/failed.manifest.json"
    mock_manifest.run_id = "failed_run"
    mock_manifest.segments = {}

    seg = TranslationOutput(segment_id="1", draft_translation="", polished_translation="")
    mock_result = ChapterResult(
        chapter_title="Failed",
        source_text="source",
        segment_results=[seg],
        aggregated_translation="",
        chapter_status=ChapterStatus.FAILED,
        segment_statuses={"1": SegmentStatus.FAILED},
        failed_segment_ids=["1"],
        manifest=mock_manifest,
        resumable=True,
    )
    mock_orchestrator.run_with_manifest.return_value = mock_result

    response = client.post("/translate/chapter", json={"source_text": "source"})
    assert response.status_code == 200
    data = response.json()

    summary = data["readable_summary"]
    assert "failed" in summary
    assert "0/1 segments completed" in summary
    assert "all 1 segments" in summary or "all segments" in summary
    assert "processes 1 remaining" in summary


@patch('app.service.draft_service.ChapterOrchestrator')
def test_chapter_readable_summary_consistency_found(mock_orchestrator_class):
    """readable_summary should include consistency audit and correction details when present."""
    mock_orchestrator = MagicMock()
    mock_orchestrator_class.return_value = mock_orchestrator

    seg = TranslationOutput(segment_id="1", draft_translation="", polished_translation="Content.")
    mock_result = ChapterResult(
        chapter_title="Test",
        source_text="source",
        segment_results=[seg],
        aggregated_translation="Content.",
        chapter_status=ChapterStatus.COMPLETED,
        segment_statuses={"1": SegmentStatus.COMPLETED},
        consistency_audit={
            "total_issues": 3,
            "by_category": {"name_variant": 2, "term_variant": 1},
            "auto_fixable": 2,
            "auto_fixed": 2,
        },
        correction_summary={
            "total_corrections": 2,
            "total_replacements": 3,
            "by_category": {"name_variant": 1, "term_variant": 1},
        },
        corrected_translation="Corrected content.",
    )
    mock_orchestrator.run_with_manifest.return_value = mock_result

    response = client.post("/translate/chapter", json={"source_text": "source"})
    assert response.status_code == 200
    data = response.json()

    summary = data["readable_summary"]
    assert "completed" in summary
    assert "3 issues" in summary
    assert "2 auto-fixed" in summary
    assert "name_variant" in summary
    assert "term_variant" in summary
    assert "Corrections:" in summary
    assert "Corrected:" in summary or "corrected" in summary.lower() or "post-consistency" in summary
    # Pre-consistency label should appear since corrected_translation is set
    assert "pre-consistency" in summary


@patch('app.service.draft_service.ChapterOrchestrator')
def test_chapter_readable_summary_strategy(mock_orchestrator_class):
    """readable_summary should include strategy overview when strategy_plan_summary is present."""
    mock_orchestrator = MagicMock()
    mock_orchestrator_class.return_value = mock_orchestrator

    seg = TranslationOutput(segment_id="1", draft_translation="", polished_translation="Content.")
    mock_result = ChapterResult(
        chapter_title="Test",
        source_text="source",
        segment_results=[seg],
        aggregated_translation="Content.",
        chapter_status=ChapterStatus.COMPLETED,
        segment_statuses={"1": SegmentStatus.COMPLETED},
        strategy_plan_summary={
            "complexity": {"level": "medium", "score": 0.45},
            "overall_strategy": {
                "processing_mode": "standard",
                "budget_profile": "conservative",
                "consistency_intensity": "enhanced",
            },
        },
    )
    mock_orchestrator.run_with_manifest.return_value = mock_result

    response = client.post("/translate/chapter", json={"source_text": "source"})
    assert response.status_code == 200
    data = response.json()

    summary = data["readable_summary"]
    assert "completed" in summary
    assert "Strategy:" in summary
    assert "complexity=medium" in summary
    assert "mode=standard" in summary
    assert "budget=conservative" in summary
    assert "consistency=enhanced" in summary


def test_translate_chapter_endpoint_missing_source_text_field():
    """Missing source_text field should return 422."""
    payload = {}
    response = client.post("/translate/chapter", json=payload)
    assert response.status_code == 422


# ── Manifest / resume semantics (Batch 5C) ────────────────────────────────


def _make_completed_result(manifest=None, run_id="run_xyz", manifest_path=None):
    """Helper to build a minimal completed ChapterResult for endpoint tests."""
    seg = TranslationOutput(segment_id="1", draft_translation="", polished_translation="Done.")
    if manifest is None:
        manifest = MagicMock()
        manifest.run_id = run_id
        manifest.manifest_path = manifest_path
        manifest.segments = {}
    return ChapterResult(
        chapter_title="Test",
        source_text="src",
        segment_results=[seg],
        aggregated_translation="Done.",
        chapter_status=ChapterStatus.COMPLETED,
        segment_statuses={"1": SegmentStatus.COMPLETED},
        manifest=manifest,
        failed_segment_ids=[],
        resumable=False,
    )


@patch('app.service.draft_service.ChapterOrchestrator')
def test_chapter_endpoint_fresh_run_with_manifest_path(mock_cls):
    """manifest_path is forwarded to orchestrator and surfaces in the response."""
    mock_orch = MagicMock()
    mock_cls.return_value = mock_orch

    fake_manifest = MagicMock()
    fake_manifest.run_id = "abcd1234"
    fake_manifest.manifest_path = "/tmp/test.manifest.json"
    fake_manifest.segments = {}
    mock_orch.run_with_manifest.return_value = _make_completed_result(manifest=fake_manifest)

    payload = {
        "source_text": "测试",
        "manifest_path": "/tmp/test.manifest.json",
    }
    response = client.post("/translate/chapter", json=payload)
    assert response.status_code == 200
    data = response.json()
    assert data["manifest_path"] == "/tmp/test.manifest.json"
    assert data["run_id"] == "abcd1234"

    # Orchestrator was called with manifest_path forwarded; no resume.
    mock_orch.run_with_manifest.assert_called_once()
    kwargs = mock_orch.run_with_manifest.call_args.kwargs
    assert kwargs["manifest_path"] == "/tmp/test.manifest.json"
    assert kwargs["source_text"] == "测试"
    assert kwargs.get("existing_manifest") is None
    # No resume_config overrides were sent → orchestrator gets None (defaults).
    assert kwargs.get("resume_config") is None
    mock_orch.load_manifest.assert_not_called()


@patch('app.service.draft_service.ChapterOrchestrator')
def test_chapter_endpoint_fresh_run_without_manifest_path(mock_cls):
    """Default fresh run without manifest_path stays in-memory (no persistence)."""
    mock_orch = MagicMock()
    mock_cls.return_value = mock_orch
    mock_orch.run_with_manifest.return_value = _make_completed_result()

    response = client.post("/translate/chapter", json={"source_text": "src"})
    assert response.status_code == 200
    kwargs = mock_orch.run_with_manifest.call_args.kwargs
    assert kwargs["manifest_path"] is None


@patch('app.service.draft_service.ChapterOrchestrator')
def test_chapter_endpoint_resume_requires_manifest_path(mock_cls):
    """resume=true without manifest_path is a 400 client error."""
    response = client.post("/translate/chapter", json={
        "source_text": "src",
        "resume": True,
    })
    assert response.status_code == 400
    assert "manifest_path is required" in response.json()["detail"]
    mock_cls.assert_not_called()


@patch('app.service.draft_service.ChapterOrchestrator')
def test_chapter_endpoint_resume_manifest_missing(mock_cls):
    """resume=true with a missing manifest is a 404."""
    mock_orch = MagicMock()
    mock_cls.return_value = mock_orch
    mock_orch.load_manifest.return_value = None

    response = client.post("/translate/chapter", json={
        "source_text": "src",
        "resume": True,
        "manifest_path": "/tmp/missing.manifest.json",
    })
    assert response.status_code == 404
    assert "/tmp/missing.manifest.json" in response.json()["detail"]
    mock_orch.run_with_manifest.assert_not_called()


@patch('app.service.draft_service.ChapterOrchestrator')
def test_chapter_endpoint_resume_manifest_not_resumable(mock_cls):
    """resume=true on a non-resumable (e.g. completed) manifest is a 409."""
    mock_orch = MagicMock()
    mock_cls.return_value = mock_orch

    completed_manifest = MagicMock()
    completed_manifest.is_resumable.return_value = False
    completed_manifest.status = ChapterStatus.COMPLETED
    mock_orch.load_manifest.return_value = completed_manifest

    response = client.post("/translate/chapter", json={
        "source_text": "src",
        "resume": True,
        "manifest_path": "/tmp/done.manifest.json",
    })
    assert response.status_code == 409
    assert "not resumable" in response.json()["detail"]
    mock_orch.run_with_manifest.assert_not_called()


@patch('app.service.draft_service.ChapterOrchestrator')
def test_chapter_endpoint_resume_continues_from_existing_manifest(mock_cls):
    """resume=true on a resumable manifest forwards it as existing_manifest."""
    mock_orch = MagicMock()
    mock_cls.return_value = mock_orch

    saved_manifest = MagicMock()
    saved_manifest.is_resumable.return_value = True
    saved_manifest.status = ChapterStatus.PARTIAL
    saved_manifest.run_id = "saved_run"
    saved_manifest.manifest_path = "/tmp/wip.manifest.json"
    saved_manifest.segments = {}
    mock_orch.load_manifest.return_value = saved_manifest
    mock_orch.run_with_manifest.return_value = _make_completed_result(manifest=saved_manifest)

    response = client.post("/translate/chapter", json={
        "source_text": "src",
        "resume": True,
        "manifest_path": "/tmp/wip.manifest.json",
    })
    assert response.status_code == 200
    data = response.json()
    assert data["run_id"] == "saved_run"
    assert data["manifest_path"] == "/tmp/wip.manifest.json"

    mock_orch.load_manifest.assert_called_once_with("/tmp/wip.manifest.json")
    kwargs = mock_orch.run_with_manifest.call_args.kwargs
    assert kwargs["existing_manifest"] is saved_manifest
    assert kwargs["manifest_path"] == "/tmp/wip.manifest.json"


@patch('app.service.draft_service.ChapterOrchestrator')
def test_chapter_endpoint_resume_config_overrides_forwarded(mock_cls):
    """ResumeConfig overrides on a fresh run are forwarded to the orchestrator."""
    mock_orch = MagicMock()
    mock_cls.return_value = mock_orch
    mock_orch.run_with_manifest.return_value = _make_completed_result()

    response = client.post("/translate/chapter", json={
        "source_text": "src",
        "max_retries": 5,
        "retry_delay_seconds": 0,
        "auto_retry_on_resume": False,
    })
    assert response.status_code == 200
    kwargs = mock_orch.run_with_manifest.call_args.kwargs
    rc = kwargs["resume_config"]
    assert rc is not None
    assert rc.max_retries == 5
    assert rc.retry_delay_seconds == 0
    assert rc.auto_retry_on_resume is False


def test_chapter_endpoint_invalid_max_retries():
    """Negative max_retries returns a 400 before the orchestrator runs."""
    response = client.post("/translate/chapter", json={
        "source_text": "src",
        "max_retries": -1,
    })
    assert response.status_code == 400
    assert "max_retries" in response.json()["detail"]


def test_chapter_endpoint_invalid_retry_delay():
    """Negative retry_delay_seconds returns a 400 before the orchestrator runs."""
    response = client.post("/translate/chapter", json={
        "source_text": "src",
        "retry_delay_seconds": -0.5,
    })
    assert response.status_code == 400
    assert "retry_delay_seconds" in response.json()["detail"]


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
