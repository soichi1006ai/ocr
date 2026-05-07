"""Tests for knowledge/kyuujitai.json"""
import json
from pathlib import Path

import pytest

KNOWLEDGE_DIR = Path(__file__).parent.parent / "knowledge"
KYUUJITAI_PATH = KNOWLEDGE_DIR / "kyuujitai.json"

REQUIRED_MAPPINGS = {
    "國": "国", "學": "学", "經": "経", "體": "体",
    "發": "発", "傳": "伝", "寶": "宝", "萬": "万",
    "曆": "暦", "祿": "禄", "德": "徳", "應": "応",
    "寬": "寛",
}


@pytest.fixture(scope="module")
def data():
    return json.loads(KYUUJITAI_PATH.read_text(encoding="utf-8"))


@pytest.fixture(scope="module")
def mapping(data):
    return {item["old"]: item["new"] for item in data["items"]}


def test_file_exists():
    assert KYUUJITAI_PATH.exists()


def test_minimum_50_entries(data):
    assert len(data["items"]) >= 50, f"Only {len(data['items'])} entries (need ≥50)"


def test_old_ne_new(data):
    """旧字体と新字体は必ず異なる"""
    bad = [item for item in data["items"] if item["old"] == item["new"]]
    assert not bad, f"old==new found: {[b['old'] for b in bad]}"


def test_no_duplicate_old(data):
    olds = [item["old"] for item in data["items"]]
    assert len(olds) == len(set(olds)), "Duplicate 'old' characters found"


def test_required_mappings(mapping):
    for old, expected_new in REQUIRED_MAPPINGS.items():
        assert old in mapping, f"Required mapping missing: {old}"
        assert mapping[old] == expected_new, (
            f"{old} → {mapping[old]} but expected {expected_new}"
        )


def test_single_char_entries(data):
    for item in data["items"]:
        assert len(item["old"]) == 1, f"old must be 1 char: {item['old']!r}"
        assert len(item["new"]) == 1, f"new must be 1 char: {item['new']!r}"


def test_gengou_kyuujitai_covered(mapping):
    """元号で使われる旧字体が全てカバーされている"""
    gengou_chars = {"寶", "萬", "曆", "祿", "德", "應", "寬"}
    missing = gengou_chars - set(mapping.keys())
    assert not missing, f"Gengou 旧字体 missing: {missing}"
