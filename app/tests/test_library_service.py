"""Tests for the library / book-import HTTP endpoints.

Covers POST /api/books, GET /api/books/{book_id}, and
GET /api/books/{book_id}/chapters/{index}. Each test points
LIBRARY_ROOT at a per-test tmp_path so book workspaces stay isolated.
"""
from __future__ import annotations

import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

try:
    from fastapi.testclient import TestClient
    from app.service.draft_service import app, MAX_BOOK_BYTES
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
def isolated_library(monkeypatch, tmp_path):
    """Point LIBRARY_ROOT at a tmp dir for the duration of the test."""
    monkeypatch.setenv("LIBRARY_ROOT", str(tmp_path))
    return tmp_path


def _upload(filename: str, content: bytes, content_type: str = "text/plain"):
    return client.post(
        "/api/books",
        files={"file": (filename, content, content_type)},
    )


def test_post_books_happy_path(isolated_library):
    response = _upload("某某传.txt", THREE_CHAPTER_TEXT.encode("utf-8"))
    assert response.status_code == 200, response.text
    body = response.json()

    assert body["book"]["chapter_count"] == 3
    assert body["book"]["title"] == "某某传"
    assert body["book"]["source_filename"] == "某某传.txt"
    assert body["book"]["has_preamble"] is False
    assert body["book"]["book_id"].startswith("bk_")

    job = body["job"]
    assert job["status"] == "pending"
    assert job["total_chapters"] == 3
    assert job["completed_chapter_indexes"] == []
    assert job["failed_chapter_indexes"] == []

    chapters = body["chapters"]
    assert [c["index"] for c in chapters] == [1, 2, 3]
    assert [c["heading"] for c in chapters] == ["第一章 序", "第二章 中", "第三章 末"]


def test_post_books_idempotent_on_same_content(isolated_library):
    first = _upload("a.txt", THREE_CHAPTER_TEXT.encode("utf-8")).json()
    second = _upload("b.txt", THREE_CHAPTER_TEXT.encode("utf-8")).json()
    assert first["book"]["book_id"] == second["book"]["book_id"]
    # Original filename is preserved on the persisted record.
    assert second["book"]["source_filename"] == "a.txt"


def test_post_books_records_preamble_flag(isolated_library):
    text = "封面：某某传\n作者：佚名\n\n" + THREE_CHAPTER_TEXT
    body = _upload("c.txt", text.encode("utf-8")).json()
    assert body["book"]["has_preamble"] is True
    assert body["book"]["chapter_count"] == 3


def test_post_books_rejects_empty_file(isolated_library):
    response = _upload("empty.txt", b"")
    assert response.status_code == 400
    assert "empty" in response.json()["detail"].lower()


def test_post_books_rejects_whitespace_only(isolated_library):
    response = _upload("ws.txt", "   \n\n  ".encode("utf-8"))
    assert response.status_code == 400


def test_post_books_rejects_text_without_chapter_headings(isolated_library):
    response = _upload(
        "prose.txt",
        "纯散文，没有章节标题。\n".encode("utf-8"),
    )
    assert response.status_code == 400
    assert "第N章" in response.json()["detail"] or "chapter" in response.json()["detail"].lower()


def test_post_books_rejects_non_utf8(isolated_library):
    # GBK-encoded bytes that are not valid UTF-8.
    bad = "第一章 序\n正文。\n".encode("gbk")
    response = _upload("gbk.txt", bad)
    assert response.status_code == 400
    assert "utf-8" in response.json()["detail"].lower()


def test_post_books_rejects_oversized_file(isolated_library):
    oversized = b"x" * (MAX_BOOK_BYTES + 1)
    response = _upload("big.txt", oversized)
    assert response.status_code == 413


def test_post_books_uses_fallback_filename_when_whitespace(isolated_library):
    """When the upload filename is just whitespace, fall back to a
    sensible default rather than persisting an empty string."""
    response = _upload("   ", THREE_CHAPTER_TEXT.encode("utf-8"))
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["book"]["source_filename"] == "upload.txt"
    assert body["book"]["title"] == "upload"


def test_get_book_detail(isolated_library):
    posted = _upload("某某传.txt", THREE_CHAPTER_TEXT.encode("utf-8")).json()
    book_id = posted["book"]["book_id"]

    response = client.get(f"/api/books/{book_id}")
    assert response.status_code == 200
    body = response.json()
    assert body["book"]["book_id"] == book_id
    assert body["job"]["status"] == "pending"
    assert len(body["chapters"]) == 3


def test_get_book_detail_404(isolated_library):
    response = client.get("/api/books/bk_does_not_exi")
    assert response.status_code == 404


def test_get_chapter_returns_full_source(isolated_library):
    posted = _upload("x.txt", THREE_CHAPTER_TEXT.encode("utf-8")).json()
    book_id = posted["book"]["book_id"]

    response = client.get(f"/api/books/{book_id}/chapters/2")
    assert response.status_code == 200
    body = response.json()
    assert body["index"] == 2
    assert body["heading"] == "第二章 中"
    assert body["source_text"].startswith("第二章 中")
    assert "乙段" in body["source_text"]
    # Must not bleed into chapter 3.
    assert "第三章" not in body["source_text"]


def test_get_chapter_404_for_missing_index(isolated_library):
    posted = _upload("x.txt", THREE_CHAPTER_TEXT.encode("utf-8")).json()
    book_id = posted["book"]["book_id"]

    response = client.get(f"/api/books/{book_id}/chapters/99")
    assert response.status_code == 404


def test_get_chapter_404_for_missing_book(isolated_library):
    response = client.get("/api/books/bk_does_not_exi/chapters/1")
    assert response.status_code == 404


def test_get_chapter_404_for_zero_or_negative_index(isolated_library):
    posted = _upload("x.txt", THREE_CHAPTER_TEXT.encode("utf-8")).json()
    book_id = posted["book"]["book_id"]
    assert client.get(f"/api/books/{book_id}/chapters/0").status_code == 404
    # Negative index: FastAPI may parse {index} as int; -1 should also 404.
    assert client.get(f"/api/books/{book_id}/chapters/-1").status_code == 404


def test_existing_translate_endpoints_still_registered():
    """Sanity: the new endpoints did not collide with or unregister
    any existing translation endpoints."""
    paths = {r.path for r in app.routes}
    for required in {"/translate/draft", "/translate/chapter", "/api/chapters", "/health"}:
        assert required in paths
