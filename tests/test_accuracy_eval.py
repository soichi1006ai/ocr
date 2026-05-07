"""Tests for tests/accuracy_eval.py (no actual OCR calls)"""
import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))
sys.path.insert(0, str(Path(__file__).parent))

from accuracy_eval import (
    _edit_distance,
    calc_cer,
    flatten_to_text,
    calc_struct_match,
    evaluate_pair,
    evaluate_results,
    render_markdown,
    render_json,
    list_ground_truth_files,
    load_ground_truth,
)


# ---------------------------------------------------------------------------
# _edit_distance
# ---------------------------------------------------------------------------

def test_edit_distance_equal():
    assert _edit_distance("abc", "abc") == 0


def test_edit_distance_empty_s1():
    assert _edit_distance("", "abc") == 3


def test_edit_distance_empty_s2():
    assert _edit_distance("abc", "") == 3


def test_edit_distance_substitution():
    assert _edit_distance("abc", "axc") == 1


def test_edit_distance_insertion():
    assert _edit_distance("ac", "abc") == 1


def test_edit_distance_deletion():
    assert _edit_distance("abcd", "abd") == 1


def test_edit_distance_kanji():
    # 甲王 → 甲子: 1 substitution
    assert _edit_distance("甲王乙丑", "甲子乙丑") == 1


# ---------------------------------------------------------------------------
# calc_cer
# ---------------------------------------------------------------------------

def test_cer_identical():
    assert calc_cer("甲子乙丑", "甲子乙丑") == 0.0


def test_cer_one_error():
    # 1 error in 4 chars = 0.25
    assert abs(calc_cer("甲王乙丑", "甲子乙丑") - 0.25) < 1e-9


def test_cer_empty_expected():
    assert calc_cer("anything", "") == 0.0


def test_cer_all_wrong():
    cer = calc_cer("XXXX", "甲子乙丑")
    assert cer > 0.0


# ---------------------------------------------------------------------------
# flatten_to_text
# ---------------------------------------------------------------------------

def test_flatten_string():
    assert flatten_to_text("hello") == "hello"


def test_flatten_dict():
    result = flatten_to_text({"a": "甲", "b": "子"})
    assert "甲" in result and "子" in result


def test_flatten_list():
    result = flatten_to_text(["甲", "子", "乙"])
    assert result == "甲子乙"


def test_flatten_nested():
    data = {"months": [{"days": [{"kanshi": "甲子"}, {"kanshi": "乙丑"}]}]}
    result = flatten_to_text(data)
    assert "甲子" in result and "乙丑" in result


def test_flatten_ignores_non_string_leaves():
    data = {"day": 1, "confidence": 0.9, "kanshi": "甲子"}
    result = flatten_to_text(data)
    assert result == "甲子"


# ---------------------------------------------------------------------------
# calc_struct_match
# ---------------------------------------------------------------------------

def test_struct_match_identical():
    d = {"a": "x", "b": "y"}
    assert calc_struct_match(d, d) == 1.0


def test_struct_match_one_wrong():
    actual   = {"a": "x", "b": "WRONG"}
    expected = {"a": "x", "b": "y"}
    match = calc_struct_match(actual, expected)
    assert abs(match - 0.5) < 1e-9


def test_struct_match_nested():
    expected = {"months": [{"kanshi": "甲子"}]}
    actual   = {"months": [{"kanshi": "甲子"}]}
    assert calc_struct_match(actual, expected) == 1.0


def test_struct_match_partial_list():
    expected = [{"k": "甲子"}, {"k": "乙丑"}]
    actual   = [{"k": "甲子"}, {"k": "WRONG"}]
    match = calc_struct_match(actual, expected)
    assert abs(match - 0.5) < 1e-9


def test_struct_match_empty_expected():
    assert calc_struct_match({}, {}) == 1.0


# ---------------------------------------------------------------------------
# evaluate_pair
# ---------------------------------------------------------------------------

def test_evaluate_pair_identical():
    data = {"document_type": "koyomi", "year": "元禄15年"}
    metrics = evaluate_pair(data, data)
    assert metrics["cer"] == 0.0
    assert metrics["struct_match"] == 1.0


def test_evaluate_pair_partial_error():
    expected = {"year": "元禄15年"}
    actual   = {"year": "元禄15年XXX"}
    metrics  = evaluate_pair(actual, expected)
    assert metrics["cer"] > 0.0


# ---------------------------------------------------------------------------
# evaluate_results
# ---------------------------------------------------------------------------

def _make_file_result(doc_type: str, cer: float) -> dict:
    return {
        "file":          f"{doc_type}_test.json",
        "document_type": doc_type,
        "cer":           cer,
        "struct_match":  1.0,
        "char_count":    100,
    }


def test_evaluate_results_passed():
    results = [_make_file_result("koyomi", 0.005)]
    report  = evaluate_results(results, mode="cloud")
    assert report["by_document_type"]["koyomi"]["passed"] is True


def test_evaluate_results_failed():
    results = [_make_file_result("koyomi", 0.05)]
    report  = evaluate_results(results, mode="cloud")
    assert report["by_document_type"]["koyomi"]["passed"] is False


def test_evaluate_results_overall_cer():
    results = [
        _make_file_result("koyomi", 0.02),
        _make_file_result("koyomi", 0.04),
    ]
    report = evaluate_results(results, mode="cloud")
    assert abs(report["overall_cer"] - 0.03) < 1e-4


def test_evaluate_results_all_passed_false_when_any_fails():
    results = [
        _make_file_result("koyomi",  0.005),  # passes
        _make_file_result("daichou", 0.10),   # fails (target 0.03 cloud)
    ]
    report = evaluate_results(results, mode="cloud")
    assert report["all_passed"] is False


# ---------------------------------------------------------------------------
# render_markdown
# ---------------------------------------------------------------------------

def test_render_markdown_contains_headers():
    results = [_make_file_result("koyomi", 0.005)]
    report  = evaluate_results(results, mode="cloud")
    md = render_markdown([report])
    assert "# OCR 精度評価レポート" in md
    assert "koyomi" in md
    assert "cloud" in md


def test_render_markdown_shows_pass_mark():
    results = [_make_file_result("koyomi", 0.005)]
    report  = evaluate_results(results, mode="cloud")
    md = render_markdown([report])
    assert "✅" in md


def test_render_markdown_shows_fail_mark():
    results = [_make_file_result("koyomi", 0.99)]
    report  = evaluate_results(results, mode="cloud")
    md = render_markdown([report])
    assert "❌" in md


# ---------------------------------------------------------------------------
# render_json
# ---------------------------------------------------------------------------

def test_render_json_is_valid():
    results = [_make_file_result("koyomi", 0.005)]
    report  = evaluate_results(results, mode="cloud")
    raw = render_json([report])
    parsed = json.loads(raw)
    assert len(parsed) == 1
    assert parsed[0]["mode"] == "cloud"


# ---------------------------------------------------------------------------
# list_ground_truth_files
# ---------------------------------------------------------------------------

def test_list_ground_truth_files(tmp_path):
    (tmp_path / "koyomi_001.json").write_text("{}")
    (tmp_path / "koyomi_002.json").write_text("{}")
    (tmp_path / "daichou_001.json").write_text("{}")

    files = list_ground_truth_files(tmp_path)
    assert len(files["koyomi"]) == 2
    assert len(files["daichou"]) == 1


# ---------------------------------------------------------------------------
# load_ground_truth + evaluate with real fixture files
# ---------------------------------------------------------------------------

FIXTURE_DIR = Path(__file__).parent / "ground_truth"


@pytest.mark.skipif(not FIXTURE_DIR.exists(), reason="ground_truth not present")
def test_load_koyomi_001():
    data = load_ground_truth(FIXTURE_DIR / "koyomi_001.json")
    assert data["document_type"] == "koyomi"
    assert "months" in data
    assert len(data["months"]) >= 1


@pytest.mark.skipif(not FIXTURE_DIR.exists(), reason="ground_truth not present")
def test_evaluate_pair_self_koyomi_001():
    data    = load_ground_truth(FIXTURE_DIR / "koyomi_001.json")
    metrics = evaluate_pair(data, data)
    assert metrics["cer"] == 0.0
    assert metrics["struct_match"] == 1.0


@pytest.mark.skipif(not FIXTURE_DIR.exists(), reason="ground_truth not present")
def test_evaluate_pair_self_daichou_001():
    data    = load_ground_truth(FIXTURE_DIR / "daichou_001.json")
    metrics = evaluate_pair(data, data)
    assert metrics["cer"] == 0.0
    assert metrics["struct_match"] == 1.0
