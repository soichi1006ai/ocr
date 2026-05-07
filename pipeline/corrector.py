"""
pipeline/corrector.py — 干支・元号・旧字体の辞書補正

knowledge/ の各 JSON を活用して OCR 後テキストを補正する。
旧字体変換はオプショナル（デフォルト off）。
"""
from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field

from knowledge.loader import (
    apply_kyuujitai_correction,
    get_gengou_names,
    get_kanshi_set,
    load_gengou,
    load_kanshi,
)

logger = logging.getLogger(__name__)


@dataclass
class CorrectionDiff:
    """補正前後の差分を記録する"""
    original: str
    corrected: str
    changes: list[tuple[str, str]] = field(default_factory=list)  # (before, after)

    @property
    def has_changes(self) -> bool:
        return self.original != self.corrected


def correct_text(
    text: str,
    *,
    apply_kyuujitai: bool = False,
    log_diff: bool = True,
) -> CorrectionDiff:
    """
    OCR後テキストに対して辞書補正を適用する。

    Parameters
    ----------
    text:
        補正対象テキスト
    apply_kyuujitai:
        旧字体→新字体変換を行う（デフォルト: False）
    log_diff:
        差分をログ出力する
    """
    original = text
    changes: list[tuple[str, str]] = []

    # 1. 干支誤読補正
    text, kc = _correct_kanshi(text)
    changes.extend(kc)

    # 2. 元号誤読補正
    text, gc = _correct_gengou(text)
    changes.extend(gc)

    # 3. 旧字体変換（オプション）
    if apply_kyuujitai:
        corrected_kyuu = apply_kyuujitai_correction(text)
        if corrected_kyuu != text:
            changes.append((text, corrected_kyuu))
            text = corrected_kyuu

    diff = CorrectionDiff(original=original, corrected=text, changes=changes)
    if log_diff and diff.has_changes:
        logger.debug("corrector: %d changes applied", len(changes))
    return diff


def correct_structured(
    data: dict,
    *,
    apply_kyuujitai: bool = False,
) -> dict:
    """
    暦表などの構造化 JSON データに補正を適用する。
    文字列フィールドを再帰的に補正する。
    """
    return _correct_dict(data, apply_kyuujitai=apply_kyuujitai)


# ---------------------------------------------------------------------------
# Internal correction logic
# ---------------------------------------------------------------------------

def _correct_kanshi(text: str) -> tuple[str, list[tuple[str, str]]]:
    """干支の誤読パターンを正しい干支に置換する"""
    changes: list[tuple[str, str]] = []
    kanshi_items = load_kanshi()

    for item in kanshi_items:
        for mis in item.get("common_misreads", []):
            if mis in text:
                before = text
                text = text.replace(mis, item["kanji"])
                if text != before:
                    changes.append((mis, item["kanji"]))

    # 既存の硬直した誤読パターン（text_extractor.py より移植）
    static_fixes = {
        "甲王": "甲子", "乙王": "乙丑", "丙笑": "丙寅", "丁王": "丁卯",
        "戊笑": "戊寅", "庚宙": "庚申", "笑末": "癸未", "笑亥": "癸亥",
        "笑酉": "癸酉", "笑川": "癸丑", "笑未": "癸未", "茂酉": "戊酉",
        "内辰": "丙辰", "王子": "甲子", "王": "壬", "已": "己",
    }
    for src, dst in static_fixes.items():
        if src in text:
            before = text
            text = text.replace(src, dst)
            if text != before:
                changes.append((src, dst))

    return text, changes


def _correct_gengou(text: str) -> tuple[str, list[tuple[str, str]]]:
    """元号の誤読パターンを正しい元号に置換する"""
    changes: list[tuple[str, str]] = []
    gengou_items = load_gengou()

    for item in gengou_items:
        for mis in item.get("common_misreads", []):
            if mis in text and mis != item["name"]:
                before = text
                text = text.replace(mis, item["name"])
                if text != before:
                    changes.append((mis, item["name"]))

    # 静的な元号誤読（text_extractor.py より移植）
    static_gengou_fixes = {
        "寛丈": "寛文", "元ろ": "元禄", "元謙": "元禄", "宝氷": "宝永",
        "寛水": "寛永", "覚水": "寛永", "梵水": "寛永", "萬治": "万治",
        "承麿": "承応", "亭保": "享保", "魂正": "享保", "延亭": "延享",
        "延讃": "延享", "贅暦": "宝暦", "贄暦": "宝暦", "天磬": "天和",
        "天享": "天和", "駿長": "慶長", "文謙": "文政",
    }
    for src, dst in static_gengou_fixes.items():
        if src in text:
            before = text
            text = text.replace(src, dst)
            if text != before:
                changes.append((src, dst))

    return text, changes


def _correct_dict(data: dict, *, apply_kyuujitai: bool) -> dict:
    """辞書を再帰的に走査して文字列フィールドに補正を適用する"""
    result: dict = {}
    for key, value in data.items():
        if isinstance(value, str):
            diff = correct_text(value, apply_kyuujitai=apply_kyuujitai, log_diff=False)
            result[key] = diff.corrected
        elif isinstance(value, dict):
            result[key] = _correct_dict(value, apply_kyuujitai=apply_kyuujitai)
        elif isinstance(value, list):
            result[key] = _correct_list(value, apply_kyuujitai=apply_kyuujitai)
        else:
            result[key] = value
    return result


def _correct_list(data: list, *, apply_kyuujitai: bool) -> list:
    result: list = []
    for item in data:
        if isinstance(item, str):
            diff = correct_text(item, apply_kyuujitai=apply_kyuujitai, log_diff=False)
            result.append(diff.corrected)
        elif isinstance(item, dict):
            result.append(_correct_dict(item, apply_kyuujitai=apply_kyuujitai))
        elif isinstance(item, list):
            result.append(_correct_list(item, apply_kyuujitai=apply_kyuujitai))
        else:
            result.append(item)
    return result
