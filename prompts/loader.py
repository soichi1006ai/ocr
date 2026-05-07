"""
prompts/loader.py — プロンプトテンプレートのロードとコンテキスト注入

{ALL_CAPS} 形式のプレースホルダーのみ置換する（JSONの {} には干渉しない）。
"""
from __future__ import annotations

import re
from functools import lru_cache
from pathlib import Path

from knowledge.loader import (
    format_gengou_for_prompt,
    format_kanshi_for_prompt,
    format_kyuusei_for_prompt,
)

PROMPTS_DIR = Path(__file__).parent

_PLACEHOLDER_RE = re.compile(r"\{([A-Z][A-Z0-9_]*)\}")


def _default_context() -> dict[str, str]:
    return {
        "KANSHI_LIST": format_kanshi_for_prompt(),
        "GENGOU_LIST": format_gengou_for_prompt(period="edo"),
        "KYUUSEI_LIST": format_kyuusei_for_prompt(),
    }


@lru_cache(maxsize=None)
def _read_template(name: str) -> str:
    path = PROMPTS_DIR / f"{name}.md"
    if not path.exists():
        raise FileNotFoundError(f"Prompt template not found: {path}")
    return path.read_text(encoding="utf-8")


def load_prompt(name: str, **context: str) -> str:
    """
    プロンプトテンプレートをロードしてコンテキストを注入する。

    Parameters
    ----------
    name:
        テンプレートファイル名（拡張子なし）。例: "koyomi", "classify"
    **context:
        追加で注入するキーと値。デフォルト値を上書きできる。
        例: load_prompt("verify_koyomi", PREVIOUS_JSON="...", VALIDATION_ERRORS="...")
    """
    template = _read_template(name)

    ctx = _default_context()
    ctx.update(context)

    def _replace(m: re.Match) -> str:
        key = m.group(1)
        return ctx.get(key, m.group(0))

    return _PLACEHOLDER_RE.sub(_replace, template)


def clear_cache() -> None:
    _read_template.cache_clear()
