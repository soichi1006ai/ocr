"""
engines/paddle_engine.py — PaddleOCR エンジン（OCREngine Protocol 実装）

既存 text_extractor.py のロジックをそのまま活用しつつ、
新しい OCREngine Protocol に適合させる薄いラッパー。
"""
from __future__ import annotations

from pathlib import Path
from typing import Optional, Sequence

from engines.base import (
    BaseEngine,
    Block,
    DocumentType,
    ExtractionResult,
    PageError,
    PageResult,
    ProgressCallback,
)
from text_extractor import extract_text_from_images


class PaddleEngine(BaseEngine):
    """
    PaddleOCR 2.7.x ベースの OCR エンジン。
    paddleocr / paddlepaddle が未インストールの場合は ImportError を raise する。
    """

    name = "paddle"

    def __init__(self, lang: str = "japan", use_angle_cls: bool = True) -> None:
        # 遅延インポート（未インストール時にメッセージを出す）
        try:
            from text_extractor import PaddleOCREngine as _PaddleOCREngine
        except ImportError as exc:
            raise ImportError(
                "paddleocr is not installed. Run: pip install paddleocr==2.7.3 paddlepaddle==2.6.2"
            ) from exc

        self._inner = _PaddleOCREngine(lang=lang, use_angle_cls=use_angle_cls)

    def extract(
        self,
        image_paths: Sequence[Path],
        document_type: DocumentType = DocumentType.AUTO,
        on_progress: Optional[ProgressCallback] = None,
    ) -> ExtractionResult:
        def _progress(current: int, total: int) -> None:
            if on_progress is not None:
                on_progress(current, total, f"PaddleOCR page {current}/{total}")

        batch = extract_text_from_images(
            image_paths,
            engine=self._inner,
            on_progress=_progress,
        )

        pages = [_to_page_result(r, document_type) for r in batch.pages]
        errors = [PageError(e.page_number, e.error_message) for e in batch.errors]

        return ExtractionResult(
            pages=pages,
            errors=errors,
            metadata={"engine_name": self.name},
        )


# ---------------------------------------------------------------------------
# Conversion helpers
# ---------------------------------------------------------------------------

def _to_page_result(ocr_result, document_type: DocumentType) -> PageResult:
    """OCRPageResult → PageResult（既存フォーマット互換）"""
    block = Block(
        type="paragraph",
        content=ocr_result.text,
        confidence=1.0,   # PaddleOCR の生 confidence は text_extractor が捨てているため 1.0
    )
    return PageResult(
        page_number=ocr_result.page_number,
        document_type=document_type,
        blocks=[block],
        confidence=1.0,
        raw_text=ocr_result.text,
    )


def ocr_batch_to_extraction_result(batch, document_type: DocumentType = DocumentType.AUTO) -> ExtractionResult:
    """
    既存 OCRBatchResult → ExtractionResult 変換ヘルパ。
    ocr.py など既存コードから直接呼べる互換ブリッジ。
    """
    pages = [_to_page_result(r, document_type) for r in batch.pages]
    errors = [PageError(e.page_number, e.error_message) for e in batch.errors]
    return ExtractionResult(pages=pages, errors=errors, metadata={"engine_name": "paddle"})
