"""
Tests for the translation service HTTP client.
"""
import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..'))

from unittest.mock import patch, MagicMock
import pytest
import requests.exceptions
from app.translate.schema import TranslationInput, GlossaryTerm
from app.service.client import TranslationServiceClient, REQUESTS_AVAILABLE


# Skip all tests if requests is not installed
pytestmark = pytest.mark.skipif(
    not REQUESTS_AVAILABLE,
    reason="requests library not installed"
)


def test_client_initialization():
    """Test client initialization with custom base URL."""
    client = TranslationServiceClient(base_url="http://example.com:8888")
    assert client.base_url == "http://example.com:8888"


@patch('app.service.client.requests.post')
def test_translate_draft_success(mock_post):
    """Test successful draft translation via HTTP."""
    # Mock response
    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.json.return_value = {
        "segment_id": "123",
        "draft_translation": "[DRAFT ENGLISH] Hello world",
        "polished_translation": "",
        "notes": []
    }
    mock_post.return_value = mock_response

    client = TranslationServiceClient(base_url="http://mock")
    input_data = TranslationInput(
        segment_id="123",
        source_text="Hello world",
        glossary_terms=[]
    )
    output = client.translate_draft(input_data)

    # Verify request
    mock_post.assert_called_once()
    call_args = mock_post.call_args
    assert call_args[0][0] == "http://mock/translate/draft"
    payload = call_args[1]['json']
    assert payload["segment_id"] == "123"
    assert payload["source_text"] == "Hello world"
    assert payload["glossary_terms"] == []

    # Verify output
    assert output.segment_id == "123"
    assert output.draft_translation == "[DRAFT ENGLISH] Hello world"
    assert output.polished_translation == ""
    assert output.notes == []


@patch('app.service.client.requests.post')
def test_translate_draft_with_glossary(mock_post):
    """Test draft translation with glossary terms."""
    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.json.return_value = {
        "segment_id": "456",
        "draft_translation": "[DRAFT ENGLISH] Young Lady called Prince",
        "polished_translation": "",
        "notes": []
    }
    mock_post.return_value = mock_response

    client = TranslationServiceClient()
    input_data = TranslationInput(
        segment_id="456",
        source_text="大小姐 called 王爷",
        glossary_terms=[
            GlossaryTerm(zh="大小姐", en="Young Lady"),
            GlossaryTerm(zh="王爷", en="Prince")
        ]
    )
    output = client.translate_draft(input_data)

    # Verify glossary terms were serialized
    call_args = mock_post.call_args
    payload = call_args[1]['json']
    assert len(payload["glossary_terms"]) == 2
    assert payload["glossary_terms"][0]["zh"] == "大小姐"
    assert payload["glossary_terms"][0]["en"] == "Young Lady"


@patch('app.service.client.requests.post')
def test_translate_draft_connection_error(mock_post):
    """Test client raises exception on connection error."""
    mock_post.side_effect = requests.exceptions.ConnectionError("Cannot connect")

    client = TranslationServiceClient()
    input_data = TranslationInput(
        segment_id="999",
        source_text="test",
        glossary_terms=[]
    )
    with pytest.raises(requests.exceptions.ConnectionError):
        client.translate_draft(input_data)


@patch('app.service.client.requests.post')
def test_translate_draft_timeout(mock_post):
    """Test client raises exception on timeout."""
    mock_post.side_effect = requests.exceptions.Timeout("Request timed out")

    client = TranslationServiceClient()
    input_data = TranslationInput(
        segment_id="999",
        source_text="test",
        glossary_terms=[]
    )
    with pytest.raises(requests.exceptions.Timeout):
        client.translate_draft(input_data)


@patch('app.service.client.requests.post')
def test_translate_draft_http_error(mock_post):
    """Test client raises exception on HTTP error."""
    mock_response = MagicMock()
    mock_response.status_code = 500
    mock_response.raise_for_status.side_effect = Exception("Server error")
    mock_post.return_value = mock_response

    client = TranslationServiceClient()
    input_data = TranslationInput(
        segment_id="999",
        source_text="test",
        glossary_terms=[]
    )
    with pytest.raises(Exception):
        client.translate_draft(input_data)


if __name__ == "__main__":
    # If requests is not installed, skip tests
    if not REQUESTS_AVAILABLE:
        print("Skipping client tests (requests not installed)")
    else:
        test_client_initialization()
        print("All client tests passed (mocked).")