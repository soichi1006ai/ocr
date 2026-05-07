"""Tests for knowledge/gengou.json"""
import json
from pathlib import Path

import pytest

KNOWLEDGE_DIR = Path(__file__).parent.parent / "knowledge"
GENGOU_PATH = KNOWLEDGE_DIR / "gengou.json"

EDO_START_NAMES = {"慶長", "元和", "寛永", "正保", "慶安", "承応", "明暦", "万治",
                   "寛文", "延宝", "天和", "貞享", "元禄", "宝永", "正徳", "享保",
                   "元文", "寛保", "延享", "寛延", "宝暦", "明和", "安永", "天明",
                   "寛政", "享和", "文化", "文政", "天保", "弘化", "嘉永", "安政",
                   "万延", "文久", "元治", "慶応"}
MODERN_NAMES = {"明治", "大正", "昭和", "平成", "令和"}


@pytest.fixture(scope="module")
def data():
    return json.loads(GENGOU_PATH.read_text(encoding="utf-8"))


def test_file_exists():
    assert GENGOU_PATH.exists(), f"{GENGOU_PATH} not found"


def test_top_level_keys(data):
    assert "version" in data
    assert "items" in data


def test_edo_eras_present(data):
    names = {item["name"] for item in data["items"]}
    missing = EDO_START_NAMES - names
    assert not missing, f"Edo eras missing: {missing}"


def test_modern_eras_present(data):
    names = {item["name"] for item in data["items"]}
    missing = MODERN_NAMES - names
    assert not missing, f"Modern eras missing: {missing}"


def test_no_duplicate_names(data):
    names = [item["name"] for item in data["items"]]
    assert len(names) == len(set(names)), "Duplicate era names found"


def test_start_year_ascending(data):
    years = [item["start_year"] for item in data["items"]]
    assert years == sorted(years), "start_year must be ascending"


def test_no_gaps_or_overlaps(data):
    """end_year of each era must equal start_year of the next (except last)."""
    items = data["items"]
    for i in range(len(items) - 1):
        current, nxt = items[i], items[i + 1]
        assert current["end_year"] == nxt["start_year"], (
            f"{current['name']} end={current['end_year']} "
            f"!= {nxt['name']} start={nxt['start_year']}"
        )


def test_last_era_end_year_null(data):
    last = data["items"][-1]
    assert last["end_year"] is None, f"Last era end_year should be null, got {last['end_year']}"


def test_first_era(data):
    assert data["items"][0]["name"] == "慶長"
    assert data["items"][0]["start_year"] == 1596


def test_edo_period_label(data):
    for item in data["items"]:
        if item["name"] in EDO_START_NAMES:
            assert item["period"] == "edo", f"{item['name']} should be period=edo"


def test_modern_period_label(data):
    for item in data["items"]:
        if item["name"] in MODERN_NAMES:
            assert item["period"] == "modern", f"{item['name']} should be period=modern"


def test_common_misreads_nonempty(data):
    for item in data["items"]:
        assert len(item["common_misreads"]) >= 1, (
            f"{item['name']}: common_misreads is empty"
        )
