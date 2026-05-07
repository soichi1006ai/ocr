"""
pipeline/validator.py — 出力検証

暦表・台帳・本文の抽出結果に対して整合性を検証する。
エラーリストを返す（空なら OK）。
"""
from __future__ import annotations

import unicodedata
from dataclasses import dataclass
from datetime import date
from typing import Any

from knowledge.loader import get_gengou_names, get_kanshi_set, gengou_to_seireki, validate_kanshi_sequence


@dataclass
class ValidationError:
    field: str
    message: str
    severity: str = "error"  # "error" | "warning"


def validate_koyomi(result: dict) -> list[ValidationError]:
    """
    暦表抽出結果の検証。

    チェック:
    1. 日数（28〜31日）
    2. 干支60組の連続性
    3. 必須フィールドの存在
    """
    errors: list[ValidationError] = []

    if not isinstance(result, dict):
        return [ValidationError("root", "結果がdictではない")]

    # 必須フィールド
    for required in ("document_type", "months"):
        if required not in result:
            errors.append(ValidationError(required, f"必須フィールド '{required}' が存在しない"))

    months = result.get("months", [])
    if not isinstance(months, list):
        return errors + [ValidationError("months", "months はリストでなければならない")]

    all_kanshi: list[str] = []

    for month_data in months:
        if not isinstance(month_data, dict):
            continue

        month_label = month_data.get("month", "不明")
        days = month_data.get("days", [])

        if not isinstance(days, list):
            errors.append(ValidationError(
                f"{month_label}.days",
                "days はリストでなければならない"
            ))
            continue

        # 日数チェック
        day_count = len(days)
        if day_count < 28 or day_count > 31:
            errors.append(ValidationError(
                f"{month_label}.days",
                f"日数が不正: {day_count}（28〜31 であるべき）",
                severity="warning" if 25 <= day_count <= 33 else "error",
            ))

        # 干支収集
        for day_data in days:
            if isinstance(day_data, dict):
                kanshi = day_data.get("kanshi")
                if kanshi and isinstance(kanshi, str) and kanshi != "[?]":
                    all_kanshi.append(kanshi)

    # 干支連続性チェック
    if len(all_kanshi) >= 3:
        valid = validate_kanshi_sequence(all_kanshi)
        if not valid:
            errors.append(ValidationError(
                "kanshi_sequence",
                "干支の連続順序が60組の循環ルールに反している",
            ))

    return errors


def validate_daichou(result: dict) -> list[ValidationError]:
    """
    台帳抽出結果の基本検証。

    チェック:
    1. 必須フィールドの存在
    2. date フィールドに元号が含まれている場合の妥当性
    """
    errors: list[ValidationError] = []

    if not isinstance(result, dict):
        return [ValidationError("root", "結果がdictではない")]

    if "entries" not in result:
        errors.append(ValidationError("entries", "必須フィールド 'entries' が存在しない"))

    # date フィールドの元号チェック
    date_str = result.get("date")
    if date_str and isinstance(date_str, str):
        known_gengou = get_gengou_names()
        found_any = any(g in date_str for g in known_gengou)
        if not found_any and _looks_like_japanese_date(date_str):
            errors.append(ValidationError(
                "date",
                f"日付に既知の元号が見つからない: {date_str!r}",
                severity="warning",
            ))

    return errors


def validate_honbun(result: dict) -> list[ValidationError]:
    """
    本文抽出結果の基本検証。

    チェック:
    1. 必須フィールドの存在
    2. テキストが空でないか
    3. 明らかな文字化けがないか（ASCII が 70% 以上なら疑わしい）
    """
    errors: list[ValidationError] = []

    if not isinstance(result, dict):
        return [ValidationError("root", "結果がdictではない")]

    if "paragraphs" not in result and "raw_text" not in result:
        errors.append(ValidationError(
            "content",
            "paragraphs または raw_text が存在しない"
        ))

    raw = result.get("raw_text", "")
    if isinstance(raw, str):
        if not raw.strip():
            errors.append(ValidationError("raw_text", "テキストが空"))
        elif _is_mostly_ascii(raw):
            errors.append(ValidationError(
                "raw_text",
                "テキストの大部分が ASCII（文字化けの可能性）",
                severity="warning",
            ))

    return errors


def validate_result(result: dict, document_type: str) -> list[ValidationError]:
    """document_type に応じた検証関数を呼び出す"""
    validators = {
        "koyomi":  validate_koyomi,
        "daichou": validate_daichou,
        "honbun":  validate_honbun,
    }
    fn = validators.get(document_type, validate_honbun)
    return fn(result)


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _looks_like_japanese_date(s: str) -> bool:
    keywords = ("年", "月", "日", "元年")
    return any(k in s for k in keywords)


def _is_mostly_ascii(text: str) -> bool:
    if not text:
        return False
    ascii_count = sum(1 for c in text if ord(c) < 128 and not c.isspace())
    return ascii_count / max(len(text), 1) > 0.7
