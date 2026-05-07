"""Tests for knowledge/kyuusei.json"""
import json
from pathlib import Path

import pytest

KNOWLEDGE_DIR = Path(__file__).parent.parent / "knowledge"
KYUUSEI_PATH = KNOWLEDGE_DIR / "kyuusei.json"

EXPECTED_KANJI = ["一白", "二黒", "三碧", "四緑", "五黄", "六白", "七赤", "八白", "九紫"]
EXPECTED_WEEKDAYS = ["日", "月", "火", "水", "木", "金", "土"]


@pytest.fixture(scope="module")
def data():
    return json.loads(KYUUSEI_PATH.read_text(encoding="utf-8"))


def test_file_exists():
    assert KYUUSEI_PATH.exists()


def test_exactly_9_entries(data):
    assert len(data["items"]) == 9


def test_all_kanji_present(data):
    kanji_list = [item["kanji"] for item in data["items"]]
    assert kanji_list == EXPECTED_KANJI


def test_index_sequence(data):
    indices = [item["index"] for item in data["items"]]
    assert indices == list(range(1, 10))


def test_full_name_contains_kanji(data):
    for item in data["items"]:
        assert item["kanji"] in item["full_name"], (
            f"{item['kanji']}: full_name {item['full_name']!r} must contain kanji"
        )


def test_common_variants_include_full_and_short(data):
    """各エントリは short (二文字) と full (星名) の両方を variants に含む"""
    for item in data["items"]:
        variants = item["common_variants"]
        assert item["kanji"] in variants, f"{item['kanji']}: short form missing from variants"
        assert item["full_name"] in variants, f"{item['kanji']}: full_name missing from variants"


def test_common_misreads_nonempty(data):
    for item in data["items"]:
        assert len(item["common_misreads"]) >= 1, f"{item['kanji']}: common_misreads is empty"


def test_weekday_elements_present(data):
    assert "weekday_elements" in data
    assert "items" in data["weekday_elements"]


def test_all_weekdays_present(data):
    weekdays = [w["weekday"] for w in data["weekday_elements"]["items"]]
    assert weekdays == EXPECTED_WEEKDAYS


def test_element_values_valid(data):
    valid = {"木", "火", "土", "金", "水"}
    for item in data["items"]:
        assert item["element"] in valid, f"{item['kanji']}: element {item['element']!r} invalid"
    for wd in data["weekday_elements"]["items"]:
        assert wd["element"] in valid
