"""Tests for knowledge/kanshi.json"""
import json
from pathlib import Path

import pytest

KNOWLEDGE_DIR = Path(__file__).parent.parent / "knowledge"
KANSHI_PATH = KNOWLEDGE_DIR / "kanshi.json"

KAN_ORDER = ["甲","乙","丙","丁","戊","己","庚","辛","壬","癸"]
SHI_ORDER = ["子","丑","寅","卯","辰","巳","午","未","申","酉","戌","亥"]
GOGYOU_MAP = {"甲":"木","乙":"木","丙":"火","丁":"火","戊":"土","己":"土","庚":"金","辛":"金","壬":"水","癸":"水"}


@pytest.fixture(scope="module")
def data():
    return json.loads(KANSHI_PATH.read_text(encoding="utf-8"))


def test_file_exists():
    assert KANSHI_PATH.exists(), f"{KANSHI_PATH} not found"


def test_top_level_keys(data):
    assert "version" in data
    assert "items" in data


def test_exactly_60_entries(data):
    assert len(data["items"]) == 60


def test_index_sequence(data):
    indices = [item["index"] for item in data["items"]]
    assert indices == list(range(1, 61)), "index must be 1..60 in order"


def test_kanji_matches_kan_shi(data):
    for item in data["items"]:
        expected = item["kan"] + item["shi"]
        assert item["kanji"] == expected, (
            f"index {item['index']}: kanji={item['kanji']!r} but kan+shi={expected!r}"
        )


def test_gogyou_matches_kan(data):
    for item in data["items"]:
        expected = GOGYOU_MAP[item["kan"]]
        assert item["gogyou"] == expected, (
            f"index {item['index']} ({item['kanji']}): gogyou={item['gogyou']!r} expected {expected!r}"
        )


def test_kan_shi_cycle(data):
    """60干支の循環ルール: (kan_index + shi_index) は同じ奇偶でなければならない"""
    for item in data["items"]:
        ki = KAN_ORDER.index(item["kan"])
        si = SHI_ORDER.index(item["shi"])
        assert ki % 2 == si % 2, (
            f"index {item['index']} ({item['kanji']}): kan/shi parity mismatch"
        )


def test_first_and_last(data):
    assert data["items"][0]["kanji"] == "甲子"
    assert data["items"][59]["kanji"] == "癸亥"


def test_common_misreads_nonempty(data):
    for item in data["items"]:
        assert len(item["common_misreads"]) >= 1, (
            f"index {item['index']} ({item['kanji']}): common_misreads is empty"
        )


def test_no_duplicate_kanji(data):
    kanjis = [item["kanji"] for item in data["items"]]
    assert len(kanjis) == len(set(kanjis)), "duplicate kanji found"
