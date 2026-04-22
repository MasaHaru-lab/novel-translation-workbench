import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..'))

import pytest

from app.translate.project_context import (
    ASSET_NAMES,
    PROMPT_NAMES,
    load_all_assets,
    load_asset,
    load_prompt,
)


def test_load_prompts_return_nonempty_text():
    for name in PROMPT_NAMES:
        text = load_prompt(name)
        assert isinstance(text, str)
        assert text.strip(), f"Prompt {name} is empty"


def test_load_prompt_unknown_name_raises():
    with pytest.raises(ValueError):
        load_prompt("prompt_z")


def test_load_all_assets_returns_every_known_name():
    assets = load_all_assets()
    assert set(assets.keys()) == set(ASSET_NAMES)


def test_each_known_asset_resolves_on_disk():
    for name in ASSET_NAMES:
        text = load_asset(name)
        assert text is not None, f"Asset {name} not found on disk"
        assert text.strip(), f"Asset {name} is empty"


def test_load_asset_unknown_name_raises():
    with pytest.raises(ValueError):
        load_asset("nonexistent_asset")
