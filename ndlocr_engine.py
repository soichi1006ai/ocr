from __future__ import annotations

import json
import shutil
import subprocess
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Optional, Sequence

from text_extractor import OCRBatchResult, OCRPageError, OCRPageResult
from table_extractor import TableData


ProgressCallback = Callable[[int, int], None]
ErrorCallback = Callable[[int, Path, Exception], None]


class NDLOCRError(Exception):
    """Raised when ndlocr-lite processing fails."""


def find_ndlocr_bin() -> Path | None:
    """ndlocr-lite の実行ファイルを探す。"""
    # 専用 venv を優先的に探す
    candidates = [
        Path("/tmp/ndl_test/bin/ndlocr-lite"),
        Path.home() / ".ndl_venv/bin/ndlocr-lite",
    ]
    for path in candidates:
        if path.exists():
            return path
    # PATH にあれば使う
    found = shutil.which("ndlocr-lite")
    return Path(found) if found else None


def run_ndlocr(
    image_paths: Sequence[str | Path],
    *,
    on_progress: Optional[ProgressCallback] = None,
    on_error: Optional[ErrorCallback] = None,
) -> OCRBatchResult:
    """ndlocr-lite をサブプロセスで実行し OCRBatchResult を返す。"""
    ndlocr_bin = find_ndlocr_bin()
    if ndlocr_bin is None:
        raise NDLOCRError(
            "ndlocr-lite が見つかりません。"
            " /tmp/ndl_test/bin/ndlocr-lite または PATH に ndlocr-lite を用意してください。"
        )

    total = len(image_paths)
    pages: list[OCRPageResult] = []
    errors: list[OCRPageError] = []

    for index, image_path in enumerate(image_paths, start=1):
        resolved = Path(image_path).expanduser().resolve()
        page_number = _infer_page_number(resolved, fallback=index)

        try:
            text = _process_single_image(ndlocr_bin, resolved)
            pages.append(OCRPageResult(
                page_number=page_number,
                image_path=resolved,
                text=text,
            ))
        except Exception as exc:
            err = OCRPageError(
                page_number=page_number,
                image_path=resolved,
                error_message=str(exc),
            )
            errors.append(err)
            if on_error:
                on_error(page_number, resolved, exc)

        if on_progress:
            on_progress(index, total)

    return OCRBatchResult(pages=pages, errors=errors)


def extract_tables_ndlocr(
    image_paths: Sequence[str | Path],
) -> list[TableData]:
    """ndlocr-lite の JSON から表領域を抽出して TableData リストを返す。

    ndlocr-lite は表セルを個別テキスト行として検出するため、
    x 座標クラスタリングで列、y 座標クラスタリングで行を再構成する。
    """
    ndlocr_bin = find_ndlocr_bin()
    if ndlocr_bin is None:
        return []

    tables: list[TableData] = []
    for image_path in image_paths:
        resolved = Path(image_path).expanduser().resolve()
        page_number = _infer_page_number(resolved, fallback=1)

        try:
            items = _get_json_items(ndlocr_bin, resolved)
            page_tables = _reconstruct_tables(items, page_number)
            tables.extend(page_tables)
        except Exception:
            pass

    return tables


# ---------- 内部関数 ----------

def _process_single_image(ndlocr_bin: Path, image_path: Path) -> str:
    with tempfile.TemporaryDirectory() as tmp_dir:
        result = subprocess.run(
            [str(ndlocr_bin), "--sourceimg", str(image_path),
             "--output", tmp_dir, "--json-only", "--device", "cpu"],
            capture_output=True, text=True, timeout=120,
        )
        if result.returncode != 0:
            raise NDLOCRError(f"ndlocr-lite failed: {result.stderr.strip()}")

        json_files = list(Path(tmp_dir).glob("*.json"))
        if not json_files:
            raise NDLOCRError("ndlocr-lite: JSON output not found")

        data = json.loads(json_files[0].read_text(encoding="utf-8"))
        return _json_to_text(data)


def _get_json_items(ndlocr_bin: Path, image_path: Path) -> list[dict]:
    with tempfile.TemporaryDirectory() as tmp_dir:
        result = subprocess.run(
            [str(ndlocr_bin), "--sourceimg", str(image_path),
             "--output", tmp_dir, "--json-only", "--device", "cpu"],
            capture_output=True, text=True, timeout=120,
        )
        if result.returncode != 0:
            return []
        json_files = list(Path(tmp_dir).glob("*.json"))
        if not json_files:
            return []
        data = json.loads(json_files[0].read_text(encoding="utf-8"))
        items = []
        for block in data.get("contents", []):
            items.extend(block)
        return items


def _json_to_text(data: dict) -> str:
    """JSON の全テキストを読み順に並べて結合する。"""
    items = []
    for block in data.get("contents", []):
        for item in block:
            text = item.get("text", "").strip()
            if not text:
                continue
            bbox = item.get("boundingBox", [])
            # 左上座標で並べ替え（右→左の縦書き順: x降順、y昇順）
            x = bbox[0][0] if bbox else 0
            y = bbox[0][1] if bbox else 0
            items.append((-x, y, text))  # x は右→左なので負にして降順

    items.sort()
    return "\n".join(text for _, _, text in items)


def _reconstruct_tables(
    items: list[dict],
    page_number: int,
) -> list[TableData]:
    """テキスト行の bbox から表構造を推定して TableData を生成する。"""
    if not items:
        return []

    # 全行の (x中心, y中心, テキスト) を収集
    rows_data: list[tuple[float, float, str]] = []
    for item in items:
        text = item.get("text", "").strip()
        bbox = item.get("boundingBox", [])
        if not text or not bbox:
            continue
        xs = [p[0] for p in bbox]
        ys = [p[1] for p in bbox]
        x_center = (min(xs) + max(xs)) / 2
        y_center = (min(ys) + max(ys)) / 2
        rows_data.append((x_center, y_center, text))

    if not rows_data:
        return []

    # y 座標でクラスタリングして行グループを作る
    rows_data.sort(key=lambda r: r[1])
    y_values = [r[1] for r in rows_data]
    y_gap = max((max(y_values) - min(y_values)) / max(len(y_values), 1) * 1.2, 30.0)

    row_groups: list[list[tuple[float, float, str]]] = []
    current = [rows_data[0]]
    for item in rows_data[1:]:
        if item[1] - current[-1][1] <= y_gap:
            current.append(item)
        else:
            row_groups.append(current)
            current = [item]
    row_groups.append(current)

    # 各行を x 座標降順（縦書き右→左）でソート
    grid = [
        [text for _, _, text in sorted(row, key=lambda r: -r[0])]
        for row in row_groups
        if row
    ]

    if not grid:
        return []

    return [TableData(page_number=page_number, table_index=1, rows=grid)]


def _infer_page_number(image_path: Path, *, fallback: int) -> int:
    stem = image_path.stem
    if stem.startswith("page_"):
        suffix = stem.removeprefix("page_")
        if suffix.isdigit():
            return int(suffix)
    return fallback
