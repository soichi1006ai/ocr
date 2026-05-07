"""
knowledge/loader.py — ナレッジJSON読み込み・プロンプト整形・検証

全JSON は lru_cache でメモリキャッシュ。テスト時は clear_cache() で初期化。
"""
from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path

KNOWLEDGE_DIR = Path(__file__).parent


# ---------------------------------------------------------------------------
# Raw loaders (lru_cache で 1回だけ読み込む)
# ---------------------------------------------------------------------------

@lru_cache(maxsize=None)
def load_kanshi() -> list[dict]:
    return json.loads((KNOWLEDGE_DIR / "kanshi.json").read_text(encoding="utf-8"))["items"]


@lru_cache(maxsize=None)
def load_gengou() -> list[dict]:
    return json.loads((KNOWLEDGE_DIR / "gengou.json").read_text(encoding="utf-8"))["items"]


@lru_cache(maxsize=None)
def load_kyuusei() -> list[dict]:
    data = json.loads((KNOWLEDGE_DIR / "kyuusei.json").read_text(encoding="utf-8"))
    return data["items"]


@lru_cache(maxsize=None)
def load_kyuujitai() -> list[dict]:
    return json.loads((KNOWLEDGE_DIR / "kyuujitai.json").read_text(encoding="utf-8"))["items"]


def clear_cache() -> None:
    """テスト用キャッシュクリア"""
    load_kanshi.cache_clear()
    load_gengou.cache_clear()
    load_kyuusei.cache_clear()
    load_kyuujitai.cache_clear()


# ---------------------------------------------------------------------------
# Derived accessors
# ---------------------------------------------------------------------------

@lru_cache(maxsize=None)
def get_kyuujitai_map() -> dict[str, str]:
    """旧字体→新字体 の dict を返す（OCR後補正用）"""
    return {item["old"]: item["new"] for item in load_kyuujitai()}


@lru_cache(maxsize=None)
def get_kanshi_set() -> frozenset[str]:
    return frozenset(item["kanji"] for item in load_kanshi())


@lru_cache(maxsize=None)
def get_gengou_names() -> frozenset[str]:
    items = load_gengou()
    names: set[str] = set()
    for item in items:
        names.add(item["name"])
        names.update(item.get("common_variants", []))
    return frozenset(names)


# ---------------------------------------------------------------------------
# Prompt formatters
# ---------------------------------------------------------------------------

def format_kanshi_for_prompt() -> str:
    """60干支をプロンプト挿入用テキストに整形"""
    items = load_kanshi()
    lines = [f"{x['index']}. {x['kanji']}（{x['yomi']}）" for x in items]
    return "\n".join(lines)


def format_gengou_for_prompt(period: str | None = None) -> str:
    """
    元号一覧をプロンプト挿入用テキストに整形。
    period="edo" | "modern" | None（全件）
    """
    items = load_gengou()
    if period:
        items = [x for x in items if x.get("period") == period]
    lines = []
    for x in items:
        end = x["end_year"] if x["end_year"] else "現在"
        lines.append(f"- {x['name']}（{x['yomi']}）{x['start_year']}〜{end}")
    return "\n".join(lines)


def format_kyuusei_for_prompt() -> str:
    """九星一覧をプロンプト挿入用テキストに整形"""
    items = load_kyuusei()
    lines = [f"- {x['kanji']}（{x['full_name']}）" for x in items]
    return "\n".join(lines)


def format_misreads_for_prompt() -> str:
    """干支・元号の共通誤読パターンをまとめてプロンプト挿入用に整形"""
    lines = ["【干支誤読パターン（修正前→正）】"]
    for item in load_kanshi():
        for mis in item.get("common_misreads", []):
            lines.append(f"  {mis} → {item['kanji']}")
    lines.append("【元号誤読パターン】")
    for item in load_gengou():
        for mis in item.get("common_misreads", []):
            lines.append(f"  {mis} → {item['name']}")
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Validation helpers
# ---------------------------------------------------------------------------

def validate_kanshi_sequence(items: list[str]) -> bool:
    """
    干支の列が60干支の循環に従っているか検証。
    items: 連続する干支の文字列リスト（例 ["甲子","乙丑","丙寅"]）
    """
    kanshi_list = [x["kanji"] for x in load_kanshi()]
    index_map = {k: i for i, k in enumerate(kanshi_list)}

    for k in items:
        if k not in index_map:
            return False

    if len(items) < 2:
        return True

    indices = [index_map[k] for k in items]
    for i in range(len(indices) - 1):
        expected_next = (indices[i] + 1) % 60
        if indices[i + 1] != expected_next:
            return False
    return True


def gengou_to_seireki(gengou: str, nen: int) -> int | None:
    """
    元号名＋年数 → 西暦を返す。
    例: gengou_to_seireki("明治", 1) → 1868
    旧字体・variants にも対応。
    """
    for item in load_gengou():
        all_names = {item["name"]} | set(item.get("common_variants", []))
        if gengou in all_names:
            result = item["start_year"] + nen - 1
            end = item["end_year"]
            if end is not None and result > end:
                return None
            return result
    return None


def apply_kyuujitai_correction(text: str) -> str:
    """旧字体→新字体に一括変換（OCR後補正）"""
    mapping = get_kyuujitai_map()
    return text.translate(str.maketrans(mapping))
