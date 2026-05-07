"""Tests for the standalone evaluate_translation script."""
import importlib.util
from pathlib import Path

import pytest


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
    assert "caught/missed/unclear describes evaluator coverage" in block
    assert "A wrong translation is caught when you list it in bad_cases" in block
    assert "do not praise that rendering in gold_cases" in block
    assert "any span listed in bad_cases is ineligible for gold_cases" in block
    assert "linked_case null" in block
    assert "Do not over-flag exact or acceptable matches" in block
    assert "Calibrate severity" in block
    assert "drop minor polish complaints first" in block
    assert "an exact or acceptable match is also caught" in block
    assert "Do not mark a match missed or unclear" in block
    assert "correct term without an explanatory gloss" in block
    assert "correct kinship/legal relation followed by an appositive name" in block
    assert "rare body/diagnostic technical terms such as 泪堂" in block
    assert '"Tear Hall beneath her eyes" is an acceptable term-with-location' in block
    assert "not a bad_case" in block
    assert "linked_case may point to bad_cases only for actual failures" in block
    assert "linked_case must be null and the item must not be listed in bad_cases" in block
    assert "Decide caught/missed/unclear first" in block
    assert "choose linked_case only after judgment" in block
    assert "Lack of a linked_case must never" in block
    assert "Do not mark a match missed or unclear" in block
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
    assert "This checklist measures whether" in prompt
    assert "this evaluator caught the human-review signal" in prompt
    assert "prioritize diverging human-review" in prompt
    assert "Do not praise a" in prompt
    assert "Never list the same Chinese span or English rendering in both" in prompt
    assert "Exact or acceptable matches" in prompt
    assert "harmless formatting differences" in prompt
    assert "Severity calibration" in prompt
    assert "drop minor" in prompt
    assert "Exact/acceptable\n  matches use linked_case null" in prompt
    assert "do not use \"missed\" or \"unclear\" merely because" in prompt
    assert "correct term\n  without an explanatory gloss" in prompt
    assert "correct kinship/legal relation followed by\n  an appositive name" in prompt
    assert "rare body/diagnostic technical terms such as 泪堂" in prompt
    assert '"Tear Hall beneath her eyes" is an acceptable' in prompt
    assert "linked_case may point to bad_cases only when" in prompt
    assert "linked_case must be null" in prompt
    assert "Decide caught/missed/unclear first" in prompt
    assert "choose linked_case only after judgment" in prompt
    assert "Lack of a linked_case must never" in prompt
    assert 'Mark "missed"' in prompt
    assert "If no human review is provided, return an empty array" in prompt


def test_report_contract_rejects_same_source_in_bad_and_gold_cases():
    report = {
        "bad_cases": [
            {
                "chinese_original": "是福不是祸，是祸躲不过",
                "bad_translation": (
                    "If it's good fortune, you can't avoid it. "
                    "If it's disaster, you can't run from it either."
                ),
            }
        ],
        "gold_cases": [
            {
                "chinese_original": "是福不是祸，是祸躲不过",
                "excellent_translation": (
                    "Blessings and calamities come as they will -- "
                    "you can't dodge what's meant to happen."
                ),
                "why_good": "Preserves the fatalistic register.",
            }
        ],
        "human_review_checklist": [],
    }

    with pytest.raises(ValueError, match="same chinese_original"):
        evaluate_translation.validate_report_contract(report)


def test_report_contract_requires_gold_case_schema():
    report = {
        "bad_cases": [],
        "gold_cases": [
            {
                "chinese_original": "凶多吉少",
                "bad_translation": "There was little hope for them, it seemed.",
                "explanation": "Accurate but too explanatory.",
            }
        ],
        "human_review_checklist": [],
    }

    with pytest.raises(ValueError, match="gold_cases\\[0\\]"):
        evaluate_translation.validate_report_contract(report)


def test_report_contract_requires_bad_case_schema():
    report = {
        "bad_cases": [
            {
                "type": "chinese_residual",
                "chiinese_original": "竟然质疑她的本事",
                "bad_translation": "How dare they doubt her skill.",
                "explanation": "Typo key mirrors the tracked ch010 smoke artifact.",
            }
        ],
        "gold_cases": [],
        "human_review_checklist": [],
    }

    with pytest.raises(ValueError, match="bad_cases\\[0\\].*chinese_original"):
        evaluate_translation.validate_report_contract(report)


def test_caught_incorrect_signal_links_to_matching_bad_case():
    report = {
        "bad_cases": [
            {
                "type": "other",
                "chinese_original": "血光之灾",
                "bad_translation": "a minor blood accident",
                "explanation": "Morpheme-calque for Daoist omen language.",
                "suggested_fix": "an omen of bloodshed",
                "severity": "major",
            }
        ],
        "gold_cases": [],
        "human_review_checklist": [
            {
                "signal": "血光之灾 -> an omen of bloodshed",
                "judgment": "caught",
                "evidence": "Reported in bad_cases[0].",
                "linked_case": 0,
            }
        ],
    }

    evaluate_translation.validate_report_contract(report)

    report["human_review_checklist"][0]["linked_case"] = None
    with pytest.raises(ValueError, match="must link"):
        evaluate_translation.validate_report_contract(report)


def test_report_contract_rejects_checklist_link_out_of_range():
    report = {
        "bad_cases": [
            {
                "type": "other",
                "chinese_original": "血光之灾",
                "bad_translation": "a minor blood accident",
                "explanation": "Morpheme-calque for Daoist omen language.",
            }
        ],
        "gold_cases": [],
        "human_review_checklist": [
            {
                "signal": "血光之灾 -> an omen of bloodshed",
                "judgment": "caught",
                "evidence": "Claims a bad-case link.",
                "linked_case": 1,
            }
        ],
    }

    with pytest.raises(ValueError, match="linked_case out of range"):
        evaluate_translation.validate_report_contract(report)


def test_report_contract_requires_checklist_schema():
    report = {
        "bad_cases": [],
        "gold_cases": [],
        "human_review_checklist": [
            {
                "signal": "小小血光 -> minor blood calamity",
                "judgment": "caught",
                "linked_case": None,
            }
        ],
    }

    with pytest.raises(ValueError, match="human_review_checklist\\[0\\].*evidence"):
        evaluate_translation.validate_report_contract(report)


def test_report_contract_rejects_invalid_checklist_judgment():
    report = {
        "bad_cases": [],
        "gold_cases": [],
        "human_review_checklist": [
            {
                "signal": "小小血光 -> minor blood calamity",
                "judgment": "accepted",
                "evidence": "Not one of the schema enum values.",
                "linked_case": None,
            }
        ],
    }

    with pytest.raises(ValueError, match="invalid judgment"):
        evaluate_translation.validate_report_contract(report)


def test_caught_reusable_good_signal_links_to_matching_gold_case():
    report = {
        "bad_cases": [],
        "gold_cases": [
            {
                "chinese_original": "是福不是祸，是祸躲不过啊",
                "excellent_translation": (
                    "Blessings and calamities come as they will -- "
                    "you can't dodge what's meant to happen."
                ),
                "why_good": "Natural idiomatic equivalent for the proverb.",
            }
        ],
        "human_review_checklist": [
            {
                "signal": (
                    "是福不是祸，是祸躲不过啊 -> Blessings and "
                    "calamities come as they will"
                ),
                "judgment": "caught",
                "evidence": "Reported in gold_cases[0].",
                "linked_case": 0,
            }
        ],
    }

    evaluate_translation.validate_report_contract(report)

    report["human_review_checklist"][0]["linked_case"] = 1
    with pytest.raises(ValueError, match="linked_case"):
        evaluate_translation.validate_report_contract(report)


def test_caught_acceptable_no_case_signal_uses_null_link():
    report = {
        "bad_cases": [],
        "gold_cases": [],
        "human_review_checklist": [
            {
                "signal": "小小血光 -> minor blood calamity",
                "judgment": "caught",
                "evidence": "Acceptable match; no case needed.",
                "linked_case": None,
            }
        ],
    }

    evaluate_translation.validate_report_contract(report)

    report["human_review_checklist"][0]["linked_case"] = 0
    with pytest.raises(ValueError, match="linked_case"):
        evaluate_translation.validate_report_contract(report)
