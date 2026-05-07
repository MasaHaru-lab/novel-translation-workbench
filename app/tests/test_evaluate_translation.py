"""Tests for the standalone evaluate_translation script."""
import importlib.util
import json
import sys
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
    assert "human review calibration conflicts with project assets" in block
    assert "validation ground truth" in block
    assert "an exact or acceptable match is also caught" in block
    assert "Do not mark a match missed or unclear" in block
    assert "correct term without an explanatory gloss" in block
    assert "correct kinship/legal relation followed by an appositive name" in block
    assert "rare body/diagnostic technical terms such as 泪堂" in block
    assert '"Tear Hall beneath her eyes" is an acceptable term-with-location' in block
    assert "not a bad_case" in block
    assert "linked_case may point to bad_cases only for actual failures" in block
    assert "linked_case must be null and the item must not be listed in bad_cases" in block
    assert "missed checklist item must never coexist with a gold_cases item" in block
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
    assert "audit every gold_cases item against bad_cases" in prompt
    assert "Do not keep a gold case with a" in prompt
    assert "Exact or acceptable matches" in prompt
    assert "harmless formatting differences" in prompt
    assert "Severity calibration" in prompt
    assert "drop minor" in prompt
    assert "human review calibration conflicts with project assets" in prompt
    assert "validation ground truth" in prompt
    assert "Exact/acceptable\n  matches use linked_case null" in prompt
    assert "do not use \"missed\" or \"unclear\" merely because" in prompt
    assert "correct term\n  without an explanatory gloss" in prompt
    assert "correct kinship/legal relation followed by\n  an appositive name" in prompt
    assert "rare body/diagnostic technical terms such as 泪堂" in prompt
    assert '"Tear Hall beneath her eyes" is an acceptable' in prompt
    assert "linked_case may point to bad_cases only when" in prompt
    assert "linked_case must be null" in prompt
    assert "A \"missed\" checklist item must never" in prompt
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

    with pytest.raises(ValueError, match="same chinese_original") as exc_info:
        evaluate_translation.validate_report_contract(report)
    message = str(exc_info.value)
    assert "bad_cases[0].chinese_original" in message
    assert "gold_cases[0].chinese_original" in message


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


def test_caught_signal_accepts_string_link_to_matching_bad_case():
    report = {
        "bad_cases": [
            {
                "type": "other",
                "chinese_original": "脸色有几分难看",
                "bad_translation": "her expression dark",
                "explanation": "Too dark for the local context.",
            },
            {
                "type": "other",
                "chinese_original": "嫡母",
                "bad_translation": "principal mother",
                "explanation": "Human review expects legal mother.",
            },
            {
                "type": "address_drift",
                "chinese_original": "你三婶那边",
                "bad_translation": "Lady Gu's side",
                "explanation": (
                    "Human review expects preserving family-status pressure: "
                    "your third aunt's side."
                ),
            },
        ],
        "gold_cases": [],
        "human_review_checklist": [
            {
                "signal": "你三婶那边 -> your third aunt's side",
                "judgment": "caught",
                "evidence": "Reported in bad_cases[2].",
                "linked_case": "bad_cases[2]",
            }
        ],
    }

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


def test_parse_failure_writes_raw_response_debug_artifact(tmp_path, monkeypatch):
    source = tmp_path / "source.txt"
    source.write_text("第十章\n\n秦流西。", encoding="utf-8")
    translation = tmp_path / "translation.md"
    translation.write_text("Chapter Ten\n\nLiuxi Qin.", encoding="utf-8")
    assets_dir = tmp_path / "assets"
    assets_dir.mkdir()
    output = tmp_path / "ch010_contract_gate_validation.json"
    malformed = '{"score": 8.8, "bad_cases": ['

    monkeypatch.setattr(
        evaluate_translation,
        "evaluate",
        lambda *_args: (malformed, "deepseek-explicit"),
    )
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "evaluate_translation.py",
            "--source",
            str(source),
            "--translation",
            str(translation),
            "--assets-dir",
            str(assets_dir),
            "--output",
            str(output),
            "--evaluator",
            "deepseek",
        ],
    )

    with pytest.raises(SystemExit) as exc:
        evaluate_translation.main()

    debug_path = output.with_suffix(".raw_response.txt")
    assert "could not parse JSON response" in str(exc.value)
    assert str(debug_path) in str(exc.value)
    assert not output.exists()
    assert debug_path.read_text(encoding="utf-8") == malformed


def test_contract_failure_writes_rejected_report_debug_artifact(tmp_path, monkeypatch):
    source = tmp_path / "source.txt"
    source.write_text("第十章\n\n秦流西。", encoding="utf-8")
    translation = tmp_path / "translation.md"
    translation.write_text("Chapter Ten\n\nLiuxi Qin.", encoding="utf-8")
    assets_dir = tmp_path / "assets"
    assets_dir.mkdir()
    output = tmp_path / "ch010_contract_gate_validation.json"
    invalid_report = {
        "score": 8.8,
        "bad_cases": [],
        "gold_cases": [],
        "proposed_asset_updates": [],
        "human_review_checklist": [
            {
                "signal": "小小血光 -> minor blood calamity",
                "judgment": "accepted",
                "evidence": "Invalid judgment enum.",
                "linked_case": None,
            }
        ],
    }

    monkeypatch.setattr(
        evaluate_translation,
        "evaluate",
        lambda *_args: (json.dumps(invalid_report), "deepseek-explicit"),
    )
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "evaluate_translation.py",
            "--source",
            str(source),
            "--translation",
            str(translation),
            "--assets-dir",
            str(assets_dir),
            "--output",
            str(output),
            "--evaluator",
            "deepseek",
        ],
    )

    with pytest.raises(SystemExit) as exc:
        evaluate_translation.main()

    rejected_path = output.with_suffix(".contract_rejected.json")
    assert "invalid report contract" in str(exc.value)
    assert str(rejected_path) in str(exc.value)
    assert not output.exists()
    rejected = json.loads(rejected_path.read_text(encoding="utf-8"))
    assert rejected["backend"] == "deepseek-explicit"
    assert rejected["human_review_checklist"][0]["judgment"] == "accepted"


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


def test_link_caught_checklist_items_fills_unambiguous_gold_case_link():
    report = {
        "bad_cases": [],
        "gold_cases": [
            {
                "chinese_original": "人伢子",
                "excellent_translation": "servant broker",
                "why_good": "Matches the glossary entry exactly.",
            }
        ],
        "human_review_checklist": [
            {
                "signal": "人伢子 -> servant broker",
                "judgment": "caught",
                "evidence": "Translation uses servant broker.",
                "linked_case": None,
            }
        ],
    }

    evaluate_translation.link_caught_checklist_items(report)

    assert report["human_review_checklist"][0]["linked_case"] == "gold_cases[0]"
    evaluate_translation.validate_report_contract(report)


def test_link_caught_checklist_items_leaves_ambiguous_matches_for_contract():
    report = {
        "bad_cases": [
            {
                "type": "other",
                "chinese_original": "人伢子",
                "bad_translation": "servant dealer",
                "explanation": "Wrong term.",
            }
        ],
        "gold_cases": [
            {
                "chinese_original": "人伢子",
                "excellent_translation": "servant broker",
                "why_good": "Matches the glossary entry exactly.",
            }
        ],
        "human_review_checklist": [
            {
                "signal": "人伢子 -> servant broker",
                "judgment": "caught",
                "evidence": "Ambiguous generated report.",
                "linked_case": None,
            }
        ],
    }

    evaluate_translation.link_caught_checklist_items(report)

    assert report["human_review_checklist"][0]["linked_case"] is None
    with pytest.raises(ValueError, match="same chinese_original"):
        evaluate_translation.validate_report_contract(report)


def test_link_caught_checklist_items_repairs_wrong_link_with_unique_match():
    report = {
        "bad_cases": [
            {
                "type": "address_drift",
                "chinese_original": "你三婶那边",
                "bad_translation": "your third aunt's side",
                "explanation": "Wrong signal for this checklist row.",
            },
            {
                "type": "relationship_misread",
                "chinese_original": "嫡母",
                "bad_translation": "principal mother",
                "explanation": "Human review expects legal mother.",
            },
        ],
        "gold_cases": [],
        "human_review_checklist": [
            {
                "signal": "嫡母 -> legal mother",
                "judgment": "caught",
                "evidence": "Reported in bad_cases.",
                "linked_case": "bad_cases[0]",
            }
        ],
    }

    evaluate_translation.link_caught_checklist_items(report)

    assert report["human_review_checklist"][0]["linked_case"] == "bad_cases[1]"
    evaluate_translation.validate_report_contract(report)


def test_link_caught_checklist_items_keeps_wrong_link_without_unique_match():
    report = {
        "bad_cases": [
            {
                "type": "address_drift",
                "chinese_original": "你三婶那边",
                "bad_translation": "your third aunt's side",
                "explanation": "Wrong signal for this checklist row.",
            }
        ],
        "gold_cases": [],
        "human_review_checklist": [
            {
                "signal": "嫡母 -> legal mother",
                "judgment": "caught",
                "evidence": "Claims wrong linked case.",
                "linked_case": "bad_cases[0]",
            }
        ],
    }

    evaluate_translation.link_caught_checklist_items(report)

    assert report["human_review_checklist"][0]["linked_case"] == "bad_cases[0]"
    with pytest.raises(ValueError) as error:
        evaluate_translation.validate_report_contract(report)
    message = str(error.value)
    assert "linked_case='bad_cases[0]'" in message
    assert "matching_refs=[]" in message


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


def test_report_contract_rejects_missed_checklist_item_praised_in_gold_case():
    report = {
        "bad_cases": [],
        "gold_cases": [
            {
                "chinese_original": "嫡母",
                "excellent_translation": "principal mother",
                "why_good": "Claims the kinship/legal term is well handled.",
            }
        ],
        "human_review_checklist": [
            {
                "signal": "嫡母 -> legal mother",
                "judgment": "missed",
                "evidence": (
                    "The evaluator did not report that the translation used "
                    "principal mother instead of legal mother."
                ),
                "linked_case": None,
            }
        ],
    }

    with pytest.raises(ValueError, match="missed checklist item"):
        evaluate_translation.validate_report_contract(report)
