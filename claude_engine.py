from __future__ import annotations

import base64
import json
from pathlib import Path
from typing import Callable, Optional, Sequence

from text_extractor import OCRBatchResult, OCRPageError, OCRPageResult
from table_extractor import TableData

ProgressCallback = Callable[[int, int], None]
ErrorCallback = Callable[[int, Path, Exception], None]

MODEL = "claude-sonnet-4-6"

# ページ全体のテキスト書き起こし
_OCR_PROMPT = """\
この画像は日本語文書のスキャンです。画像内のすべてのテキストを正確に書き起こしてください。

ルール：
- 縦書きは右→左の列順、横書きは上→下の行順で読む
- 元号・干支・旧字体・異体字はそのまま書き起こす（変換・補正しない）
- 段落・列の区切りは改行で表現する
- 表・図・欄外の注記も含める
- 書き起こしたテキストのみ出力し、説明・コメントは不要\
"""

# 表構造の抽出
_TABLE_PROMPT = """\
この画像に表（罫線やグリッドで区切られた表形式データ）があれば抽出してください。

出力形式（JSONのみ）：
[{"rows":[["セル","セル",...],...]},...]

表がなければ [] を返してください。JSON以外は出力不要。\
"""


class ClaudeOCRError(Exception):
    pass


def run_claude_ocr(
    image_paths: Sequence[str | Path],
    *,
    api_key: Optional[str] = None,
    on_progress: Optional[ProgressCallback] = None,
    on_error: Optional[ErrorCallback] = None,
) -> OCRBatchResult:
    """Claude Vision API で各ページ画像を書き起こして OCRBatchResult を返す。"""
    try:
        import anthropic
    except ImportError as exc:
        raise ClaudeOCRError(
            "anthropic が未インストールです。pip install anthropic を実行してください。"
        ) from exc

    client = anthropic.Anthropic(api_key=api_key) if api_key else anthropic.Anthropic()

    total = len(image_paths)
    pages: list[OCRPageResult] = []
    errors: list[OCRPageError] = []

    for index, image_path in enumerate(image_paths, start=1):
        resolved = Path(image_path).expanduser().resolve()
        page_number = _infer_page_number(resolved, fallback=index)

        try:
            data, media_type = _b64_image(resolved)
            msg = client.messages.create(
                model=MODEL,
                max_tokens=4096,
                messages=[{
                    "role": "user",
                    "content": [
                        {"type": "image",
                         "source": {"type": "base64",
                                    "media_type": media_type,
                                    "data": data}},
                        {"type": "text", "text": _OCR_PROMPT},
                    ],
                }],
            )
            text = msg.content[0].text
            pages.append(OCRPageResult(
                page_number=page_number,
                image_path=resolved,
                text=text,
            ))
        except Exception as exc:
            errors.append(OCRPageError(
                page_number=page_number,
                image_path=resolved,
                error_message=str(exc),
            ))
            if on_error:
                on_error(page_number, resolved, exc)

        if on_progress:
            on_progress(index, total)

    return OCRBatchResult(pages=pages, errors=errors)


def extract_tables_claude(
    image_paths: Sequence[str | Path],
    *,
    api_key: Optional[str] = None,
) -> list[TableData]:
    """Claude Vision API で各ページの表を抽出して TableData リストを返す。"""
    try:
        import anthropic
    except ImportError:
        return []

    client = anthropic.Anthropic(api_key=api_key) if api_key else anthropic.Anthropic()
    tables: list[TableData] = []

    for image_path in image_paths:
        resolved = Path(image_path).expanduser().resolve()
        page_number = _infer_page_number(resolved, fallback=1)

        try:
            data, media_type = _b64_image(resolved)
            msg = client.messages.create(
                model=MODEL,
                max_tokens=4096,
                messages=[{
                    "role": "user",
                    "content": [
                        {"type": "image",
                         "source": {"type": "base64",
                                    "media_type": media_type,
                                    "data": data}},
                        {"type": "text", "text": _TABLE_PROMPT},
                    ],
                }],
            )
            raw = msg.content[0].text.strip()
            # コードブロックが含まれていたら中身だけ取り出す
            if "```" in raw:
                raw = raw.split("```")[1]
                if raw.startswith("json"):
                    raw = raw[4:]
            parsed: list[dict] = json.loads(raw)
            for idx, tbl in enumerate(parsed, start=1):
                rows = tbl.get("rows", [])
                if rows:
                    tables.append(TableData(
                        page_number=page_number,
                        table_index=idx,
                        rows=rows,
                    ))
        except Exception:
            pass

    return tables


# ── 内部ヘルパー ──────────────────────────────────────

def _b64_image(path: Path) -> tuple[str, str]:
    media = {
        ".png": "image/png",
        ".jpg": "image/jpeg",
        ".jpeg": "image/jpeg",
        ".tiff": "image/tiff",
        ".tif": "image/tiff",
    }.get(path.suffix.lower(), "image/png")
    return base64.standard_b64encode(path.read_bytes()).decode(), media


def _infer_page_number(image_path: Path, *, fallback: int) -> int:
    stem = image_path.stem
    if stem.startswith("page_"):
        suffix = stem.removeprefix("page_")
        for side in ("_R", "_L"):
            if suffix.endswith(side):
                suffix = suffix[: -len(side)]
                break
        if suffix.isdigit():
            return int(suffix)
    return fallback
