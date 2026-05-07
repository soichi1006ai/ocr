"""
pipeline/preprocessor.py — 画像前処理の統一レイヤー（T4.4）

既存 image_preprocessor.py と pdf_converter.py のロジックを呼び出しつつ、
Claude エンジン用（解像度保持）と Paddle エンジン用（二値化・傾き補正）を分離する。
"""
from __future__ import annotations

import logging
from pathlib import Path

logger = logging.getLogger(__name__)


def preprocess(
    image_path: Path,
    *,
    mode: str = "claude",
) -> Path:
    """
    エンジンモードに応じた前処理を行い、処理後の画像パスを返す。

    Parameters
    ----------
    image_path:
        入力画像パス
    mode:
        "claude"  — JPEG変換のみ（解像度保持）
        "paddle"  — 傾き補正 + 二値化（Paddle 専用）
    """
    if mode == "paddle":
        return _preprocess_for_paddle(image_path)
    else:
        return image_path   # Claude は _b64_image() 内で変換するのでここでは何もしない


def pdf_to_images(
    pdf_path: Path,
    output_dir: Path,
    *,
    dpi: int = 300,
) -> list[Path]:
    """
    PDF を PNG 画像群に変換する。既存 pdf_converter.py を呼び出す。

    Returns
    -------
    list[Path]
        生成された画像ファイルのリスト（ページ順）
    """
    from pdf_converter import convert_pdf_to_images

    output_dir.mkdir(parents=True, exist_ok=True)
    return convert_pdf_to_images(pdf_path, output_dir=output_dir, dpi=dpi)


# ---------------------------------------------------------------------------
# Engine-specific preprocessing
# ---------------------------------------------------------------------------

def _preprocess_for_paddle(image_path: Path) -> Path:
    """PaddleOCR 用前処理（傾き補正 + 二値化）"""
    try:
        from image_preprocessor import preprocess_image_for_ocr
        return preprocess_image_for_ocr(image_path)
    except Exception as exc:
        logger.warning("paddle preprocessing failed for %s: %s", image_path.name, exc)
        return image_path
