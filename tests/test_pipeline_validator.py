"""Tests for pipeline/validator.py"""
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))

from pipeline.validator import (
    validate_koyomi, validate_daichou, validate_honbun, validate_result, ValidationError
)


# ---------------------------------------------------------------------------
# validate_koyomi
# ---------------------------------------------------------------------------

_KANSHI_31 = [
    "甲子","乙丑","丙寅","丁卯","戊辰","己巳","庚午","辛未",
    "壬申","癸酉","甲戌","乙亥","丙子","丁丑","戊寅","己卯",
    "庚辰","辛巳","壬午","癸未","甲申","乙酉","丙戌","丁亥",
    "戊子","己丑","庚寅","辛卯","壬辰","癸巳","甲午",
]

VALID_KOYOMI = {
    "document_type": "koyomi",
    "year": "元禄15年",
    "months": [
        {
            "month": "1月",
            "days": [{"day": i, "kanshi": k} for i, k in enumerate(_KANSHI_31, start=1)],
        }
    ],
}

def test_valid_koyomi_no_errors():
    errors = validate_koyomi(VALID_KOYOMI)
    assert errors == []


def test_koyomi_missing_months():
    data = {"document_type": "koyomi"}
    errors = validate_koyomi(data)
    assert any(e.field == "months" for e in errors)


def test_koyomi_wrong_day_count():
    data = {
        "document_type": "koyomi",
        "months": [{"month": "1月", "days": [{"day": i, "kanshi": "甲子"} for i in range(5)]}]
    }
    errors = validate_koyomi(data)
    assert any("日数" in e.message for e in errors)


def test_koyomi_invalid_kanshi_sequence():
    data = {
        "document_type": "koyomi",
        "months": [
            {"month": "1月", "days": [
                {"day": 1, "kanshi": "甲子"},
                {"day": 2, "kanshi": "丙寅"},  # 乙丑をスキップ → 不正
                {"day": 3, "kanshi": "丁卯"},
            ]}
        ]
    }
    errors = validate_koyomi(data)
    assert any("干支" in e.message for e in errors)


def test_koyomi_unknown_kanshi_ignored():
    """[?] は検証から除外される"""
    data = {
        "document_type": "koyomi",
        "months": [
            {"month": "1月", "days": [
                {"day": 1, "kanshi": "[?]"},
                {"day": 2, "kanshi": "[?]"},
            ]}
        ]
    }
    errors = validate_koyomi(data)
    kanshi_errors = [e for e in errors if "干支" in e.message]
    assert kanshi_errors == []


def test_koyomi_not_dict():
    errors = validate_koyomi("not a dict")
    assert len(errors) == 1


# ---------------------------------------------------------------------------
# validate_daichou
# ---------------------------------------------------------------------------

def test_valid_daichou_no_errors():
    data = {"document_type": "daichou", "date": "元禄5年", "entries": []}
    errors = validate_daichou(data)
    assert errors == []


def test_daichou_missing_entries():
    data = {"document_type": "daichou"}
    errors = validate_daichou(data)
    assert any(e.field == "entries" for e in errors)


def test_daichou_unknown_gengou_warning():
    data = {"document_type": "daichou", "date": "謎年3月", "entries": []}
    errors = validate_daichou(data)
    date_warnings = [e for e in errors if e.field == "date"]
    assert len(date_warnings) == 1
    assert date_warnings[0].severity == "warning"


# ---------------------------------------------------------------------------
# validate_honbun
# ---------------------------------------------------------------------------

def test_valid_honbun_no_errors():
    data = {"document_type": "honbun", "raw_text": "江戸時代の古文書である。", "paragraphs": []}
    errors = validate_honbun(data)
    assert errors == []


def test_honbun_empty_text():
    data = {"raw_text": "", "paragraphs": []}
    errors = validate_honbun(data)
    assert any("空" in e.message for e in errors)


def test_honbun_ascii_gibberish():
    data = {"raw_text": "AAABBBCCCDDDEEE" * 5, "paragraphs": []}
    errors = validate_honbun(data)
    warnings = [e for e in errors if e.severity == "warning"]
    assert len(warnings) == 1


def test_honbun_no_content_fields():
    data = {"document_type": "honbun"}
    errors = validate_honbun(data)
    assert any("content" in e.field for e in errors)


# ---------------------------------------------------------------------------
# validate_result dispatcher
# ---------------------------------------------------------------------------

def test_validate_result_dispatches_koyomi():
    data = {"document_type": "koyomi"}
    errors = validate_result(data, "koyomi")
    assert any(e.field == "months" for e in errors)


def test_validate_result_unknown_type_uses_honbun():
    data = {"raw_text": "テスト", "paragraphs": []}
    errors = validate_result(data, "unknown_type")
    assert errors == []
