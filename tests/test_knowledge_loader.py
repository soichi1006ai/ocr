"""Tests for knowledge/loader.py"""
import pytest
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from knowledge.loader import (
    load_kanshi, load_gengou, load_kyuusei, load_kyuujitai,
    get_kyuujitai_map, get_kanshi_set, get_gengou_names,
    format_kanshi_for_prompt, format_gengou_for_prompt,
    format_kyuusei_for_prompt, format_misreads_for_prompt,
    validate_kanshi_sequence, gengou_to_seireki,
    apply_kyuujitai_correction, clear_cache,
)


@pytest.fixture(autouse=True)
def reset_cache():
    clear_cache()
    yield
    clear_cache()


# --- raw loaders ---

def test_load_kanshi_returns_60():
    assert len(load_kanshi()) == 60


def test_load_gengou_returns_items():
    items = load_gengou()
    assert len(items) >= 40


def test_load_kyuusei_returns_9():
    assert len(load_kyuusei()) == 9


def test_load_kyuujitai_returns_50plus():
    assert len(load_kyuujitai()) >= 50


def test_lru_cache_same_object():
    """2回呼んでも同じオブジェクトが返る（キャッシュ確認）"""
    assert load_kanshi() is load_kanshi()


# --- derived accessors ---

def test_get_kyuujitai_map_type():
    m = get_kyuujitai_map()
    assert isinstance(m, dict)
    assert m["國"] == "国"
    assert m["學"] == "学"


def test_get_kanshi_set():
    s = get_kanshi_set()
    assert "甲子" in s
    assert "癸亥" in s
    assert len(s) == 60


def test_get_gengou_names_includes_variants():
    names = get_gengou_names()
    assert "元禄" in names
    assert "元祿" in names   # variant
    assert "慶応" in names
    assert "慶應" in names   # variant


# --- prompt formatters ---

def test_format_kanshi_for_prompt():
    text = format_kanshi_for_prompt()
    assert "甲子" in text
    assert "癸亥" in text
    lines = text.strip().split("\n")
    assert len(lines) == 60


def test_format_gengou_for_prompt_all():
    text = format_gengou_for_prompt()
    assert "元禄" in text
    assert "明治" in text


def test_format_gengou_for_prompt_edo_only():
    text = format_gengou_for_prompt(period="edo")
    assert "元禄" in text
    assert "明治" not in text


def test_format_gengou_for_prompt_modern_only():
    text = format_gengou_for_prompt(period="modern")
    assert "明治" in text
    assert "元禄" not in text


def test_format_kyuusei_for_prompt():
    text = format_kyuusei_for_prompt()
    assert "一白" in text
    assert "九紫" in text
    lines = text.strip().split("\n")
    assert len(lines) == 9


def test_format_misreads_for_prompt():
    text = format_misreads_for_prompt()
    assert "干支誤読" in text
    assert "元号誤読" in text


# --- validation ---

def test_validate_kanshi_sequence_valid():
    assert validate_kanshi_sequence(["甲子", "乙丑", "丙寅"]) is True


def test_validate_kanshi_sequence_wraparound():
    assert validate_kanshi_sequence(["壬戌", "癸亥", "甲子"]) is True


def test_validate_kanshi_sequence_invalid_skip():
    assert validate_kanshi_sequence(["甲子", "丙寅"]) is False


def test_validate_kanshi_sequence_single():
    assert validate_kanshi_sequence(["甲子"]) is True


def test_validate_kanshi_sequence_unknown():
    assert validate_kanshi_sequence(["甲子", "存在しない"]) is False


# --- gengou_to_seireki ---

def test_gengou_to_seireki_known():
    assert gengou_to_seireki("明治", 1) == 1868
    assert gengou_to_seireki("明治", 45) == 1912
    assert gengou_to_seireki("昭和", 64) == 1989


def test_gengou_to_seireki_variant():
    assert gengou_to_seireki("慶應", 1) == gengou_to_seireki("慶応", 1)


def test_gengou_to_seireki_out_of_range():
    assert gengou_to_seireki("明治", 100) is None


def test_gengou_to_seireki_unknown():
    assert gengou_to_seireki("存在しない", 1) is None


def test_gengou_to_seireki_reiwa():
    assert gengou_to_seireki("令和", 1) == 2019
    assert gengou_to_seireki("令和", 7) == 2025


# --- apply_kyuujitai_correction ---

def test_apply_kyuujitai_correction():
    assert apply_kyuujitai_correction("國學") == "国学"
    assert apply_kyuujitai_correction("寬永寶暦") == "寛永宝暦"
    assert apply_kyuujitai_correction("普通の文章") == "普通の文章"
