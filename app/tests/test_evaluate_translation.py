"""Tests for the standalone evaluate_translation script."""
import importlib.util
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[2]
MODULE_PATH = PROJECT_ROOT / "scripts" / "evaluate_translation.py"

spec = importlib.util.spec_from_file_location("evaluate_translation", MODULE_PATH)
evaluate_translation = importlib.util.module_from_spec(spec)
assert spec.loader is not None
spec.loader.exec_module(evaluate_translation)


def test_human_review_block_requires_per_signal_checklist():
    content = (
        "- 子身残 -> damage in the line of her children\n"
        "- Title: 首断亲人吉凶 -> Her First Reading of a Relative's Fortune and Misfortune"
    )

    block = evaluate_translation.build_human_review_block(content)

    assert "Human Review Calibration Signals (must-check)" in block
    assert "Treat each bullet or line-level correction as its own signal" in block
    assert "human_review_checklist" in block
    assert "caught/missed/unclear judgment per signal" in block
    assert "do not silently skip any signal" in block
    assert content in block


def test_eval_schema_requires_human_review_checklist():
    schema = evaluate_translation.EVAL_SCHEMA

    assert "human_review_checklist" in schema["required"]

    checklist = schema["properties"]["human_review_checklist"]
    assert checklist["type"] == "array"

    item = checklist["items"]
    assert set(item["required"]) == {
        "signal",
        "judgment",
        "evidence",
        "linked_case",
    }
    assert item["properties"]["judgment"]["enum"] == [
        "caught",
        "missed",
        "unclear",
    ]


def test_prompt_template_documents_checklist_contract():
    prompt = evaluate_translation.EVAL_PROMPT_TEMPLATE

    assert '"human_review_checklist"' in prompt
    assert "include one item" in prompt
    assert "for every bullet/signal" in prompt
    assert 'Mark "missed"' in prompt
    assert "If no human review is provided, return an empty array" in prompt
