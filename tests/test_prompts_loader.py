"""Tests for prompts/loader.py"""
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))

from prompts.loader import load_prompt, clear_cache

KNOWN_PROMPTS = ["koyomi", "classify", "daichou", "honbun", "verify_koyomi"]


@pytest.fixture(autouse=True)
def reset_cache():
    clear_cache()
    yield
    clear_cache()


# --- 基本ロード ---

@pytest.mark.parametrize("name", KNOWN_PROMPTS)
def test_load_prompt_returns_string(name):
    result = load_prompt(name)
    assert isinstance(result, str)
    assert len(result) > 50


def test_load_prompt_unknown_raises():
    with pytest.raises(FileNotFoundError, match="Prompt template not found"):
        load_prompt("nonexistent_template")


# --- コンテキスト注入 ---

def test_kanshi_list_injected_in_koyomi():
    text = load_prompt("koyomi")
    assert "甲子" in text
    assert "癸亥" in text


def test_gengou_list_injected_in_koyomi():
    text = load_prompt("koyomi")
    assert "元禄" in text


def test_kyuusei_list_injected_in_koyomi():
    text = load_prompt("koyomi")
    assert "一白" in text


def test_custom_context_overrides_default():
    custom = "カスタム干支リスト"
    text = load_prompt("koyomi", KANSHI_LIST=custom)
    assert custom in text


def test_verify_koyomi_requires_custom_context():
    errors = "- 干支の順序が不正: page 1, day 5"
    prev_json = '{"document_type": "koyomi"}'
    text = load_prompt("verify_koyomi", PREVIOUS_JSON=prev_json, VALIDATION_ERRORS=errors)
    assert prev_json in text
    assert errors in text


# --- JSON の {} が壊れない ---

def test_json_braces_not_substituted():
    """テンプレート内の JSON サンプル `{...}` は展開されないこと"""
    text = load_prompt("koyomi")
    # JSON サンプルの典型的なキーが残っている
    assert '"document_type"' in text


def test_classify_prompt_has_all_doc_types():
    text = load_prompt("classify")
    assert "koyomi" in text
    assert "daichou" in text
    assert "honbun" in text


def test_honbun_prompt_has_rules():
    text = load_prompt("honbun")
    assert "旧字体" in text


def test_daichou_prompt_has_gengou():
    text = load_prompt("daichou")
    assert "元号" in text


# --- キャッシュ ---

def test_lru_cache_same_content():
    a = load_prompt("classify")
    b = load_prompt("classify")
    assert a == b


def test_unknown_placeholder_left_as_is():
    """存在しないプレースホルダーはそのまま残る"""
    text = load_prompt("verify_koyomi")
    # PREVIOUS_JSON と VALIDATION_ERRORS を渡さなければそのまま残る
    assert "{PREVIOUS_JSON}" in text
