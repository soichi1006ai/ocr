"""Tests for pipeline/corrector.py"""
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))

from pipeline.corrector import correct_text, correct_structured, CorrectionDiff


# --- correct_text ---

def test_no_changes_when_clean():
    diff = correct_text("元禄十五年甲子")
    assert not diff.has_changes
    assert diff.corrected == "元禄十五年甲子"


def test_kanshi_misread_corrected():
    diff = correct_text("甲王乙丑丙寅")  # 甲王 → 甲子
    assert diff.corrected == "甲子乙丑丙寅"
    assert diff.has_changes


def test_gengou_misread_corrected():
    diff = correct_text("寛丈元年")  # 寛丈 → 寛文
    assert "寛文" in diff.corrected
    assert diff.has_changes


def test_kyuujitai_off_by_default():
    diff = correct_text("國學")
    assert "國學" in diff.corrected  # 変換しない


def test_kyuujitai_on():
    diff = correct_text("國學", apply_kyuujitai=True)
    assert diff.corrected == "国学"
    assert diff.has_changes


def test_correction_diff_changes_list():
    diff = correct_text("甲王")
    assert any("甲王" in c[0] for c in diff.changes)


# --- correct_structured ---

def test_correct_structured_string_fields():
    data = {"year": "寛丈元年", "months": []}
    result = correct_structured(data)
    assert "寛文" in result["year"]


def test_correct_structured_nested():
    data = {
        "months": [
            {"month": "1月", "days": [{"kanshi": "甲王"}]}
        ]
    }
    result = correct_structured(data)
    assert result["months"][0]["days"][0]["kanshi"] == "甲子"


def test_correct_structured_preserves_non_string():
    data = {"day": 1, "confidence": 0.9, "tags": ["a", "b"]}
    result = correct_structured(data)
    assert result["day"] == 1
    assert result["confidence"] == 0.9


def test_correct_structured_kyuujitai_off():
    data = {"text": "國學"}
    result = correct_structured(data)
    assert result["text"] == "國學"


def test_correct_structured_kyuujitai_on():
    data = {"text": "國學"}
    result = correct_structured(data, apply_kyuujitai=True)
    assert result["text"] == "国学"
