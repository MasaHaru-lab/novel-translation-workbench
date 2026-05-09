"""Tests for POST /api/books/{book_id}/translate-next.

CHAPTER_API_MODE is forced to "smoke" so the endpoint runs through
the existing smoke-mode helper and never hits a real model backend.
LIBRARY_ROOT is per-test tmp_path.
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

try:
    from fastapi.testclient import TestClient
    from app.service.draft_service import app
    FASTAPI_AVAILABLE = True
except ImportError:
    FASTAPI_AVAILABLE = False

if not FASTAPI_AVAILABLE:
    pytest.skip("FastAPI not installed", allow_module_level=True)


client = TestClient(app)


THREE_CHAPTER_TEXT = (
    "第一章 序\n"
    "甲段。\n"
    "\n"
    "第二章 中\n"
    "乙段。\n"
    "\n"
    "第三章 末\n"
    "丙段。\n"
)


@pytest.fixture
def smoke_workspace(monkeypatch, tmp_path):
    """Per-test isolated workspace + smoke-mode routing."""
    monkeypatch.setenv("LIBRARY_ROOT", str(tmp_path))
    monkeypatch.setenv("CHAPTER_API_MODE", "smoke")
    return tmp_path


def _import_three_chapter_book() -> str:
    response = client.post(
        "/api/books",
        files={"file": ("某某传.txt", THREE_CHAPTER_TEXT.encode("utf-8"), "text/plain")},
    )
    assert response.status_code == 200, response.text
    return response.json()["book"]["book_id"]


def test_translate_next_first_call_runs_chapter_one(smoke_workspace):
    book_id = _import_three_chapter_book()
    response = client.post(f"/api/books/{book_id}/translate-next")
    assert response.status_code == 200, response.text
    body = response.json()

    assert body["book_id"] == book_id
    assert body["ran_index"] == 1
    assert body["success"] is True
    assert body["chapter_status"] == "completed"
    assert body["error_message"] is None
    assert body["output_filename"] is not None
    assert body["output_filename"].startswith("translations/0001_")
    assert body["output_filename"].endswith("_en.md")

    job = body["book"]["job"]
    assert job["completed_chapter_indexes"] == [1]
    assert job["failed_chapter_indexes"] == []
    assert job["status"] == "running"


def test_translate_next_writes_output_under_workspace(smoke_workspace):
    book_id = _import_three_chapter_book()
    body = client.post(f"/api/books/{book_id}/translate-next").json()
    output_rel = body["output_filename"]
    full = smoke_workspace / book_id / output_rel
    assert full.exists()
    assert full.read_text(encoding="utf-8").strip() != ""
    # Manifest sits next to the .md.
    manifest = full.with_suffix("").with_suffix(".manifest.json")
    assert manifest.exists()


def test_translate_next_advances_sequentially(smoke_workspace):
    book_id = _import_three_chapter_book()
    indexes = []
    for _ in range(3):
        body = client.post(f"/api/books/{book_id}/translate-next").json()
        indexes.append(body["ran_index"])
    assert indexes == [1, 2, 3]
    final_job = client.post(f"/api/books/{book_id}/translate-next").json()["book"]["job"]
    assert final_job["status"] == "complete"
    assert final_job["completed_chapter_indexes"] == [1, 2, 3]


def test_translate_next_noop_when_book_complete(smoke_workspace):
    book_id = _import_three_chapter_book()
    for _ in range(3):
        client.post(f"/api/books/{book_id}/translate-next")
    # All done — next call is a clean no-op.
    response = client.post(f"/api/books/{book_id}/translate-next")
    assert response.status_code == 200
    body = response.json()
    assert body["ran_index"] is None
    assert body["success"] is False
    assert body["chapter_status"] is None
    assert body["error_message"] is None
    assert body["output_filename"] is None
    assert body["book"]["job"]["status"] == "complete"


def test_translate_next_unknown_book_404(smoke_workspace):
    response = client.post("/api/books/bk_does_not_exi/translate-next")
    assert response.status_code == 404


def test_translate_next_failure_is_200_with_controlled_body(monkeypatch, smoke_workspace):
    """When the underlying translation raises, the endpoint must NOT
    surface a 5xx — it should return HTTP 200 with success=false and
    an error_message describing what happened, and the job state
    should reflect the failed chapter."""
    book_id = _import_three_chapter_book()

    def boom(source_text, manifest_path):
        raise RuntimeError("simulated translator failure")

    # Replace the real adapter so the runner sees a deterministic failure.
    monkeypatch.setattr(
        "app.service.draft_service._translate_chapter_via_product_mode",
        boom,
    )
    response = client.post(f"/api/books/{book_id}/translate-next")
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["ran_index"] == 1
    assert body["success"] is False
    assert body["error_message"] is not None
    assert "simulated translator failure" in body["error_message"]
    assert body["output_filename"] is None
    job = body["book"]["job"]
    assert job["failed_chapter_indexes"] == [1]
    assert job["completed_chapter_indexes"] == []
    assert job["error_message"] is not None


def test_existing_endpoints_still_registered():
    paths = {r.path for r in app.routes}
    for required in {
        "/translate/draft",
        "/translate/chapter",
        "/api/chapters",
        "/api/books",
        "/api/books/{book_id}",
        "/api/books/{book_id}/chapters/{index}",
        "/api/books/{book_id}/translate-next",
        "/health",
    }:
        assert required in paths, f"missing route {required}"
