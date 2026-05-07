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
from text_extractor import extract_blocks_from_image, extract_text_from_images


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
        from text_extractor import _infer_page_number

        total = len(image_paths)
        pages: list[PageResult] = []
        errors: list[PageError] = []

        for idx, img_path in enumerate(image_paths, start=1):
            img_path = Path(img_path)
            page_number = _infer_page_number(img_path, fallback=idx)
            try:
                blocks_with_conf = extract_blocks_from_image(img_path, engine=self._inner)
                pages.append(_blocks_to_page_result(page_number, blocks_with_conf, document_type))
            except Exception as exc:
                errors.append(PageError(page_number, str(exc)))
            finally:
                if on_progress is not None:
                    on_progress(idx, total, f"PaddleOCR page {idx}/{total}")

        return ExtractionResult(
            pages=pages,
            errors=errors,
            metadata={"engine_name": self.name},
        )


# ---------------------------------------------------------------------------
# Conversion helpers
# ---------------------------------------------------------------------------

def _blocks_to_page_result(
    page_number: int,
    blocks_with_conf: list[tuple[str, float]],
    document_type: DocumentType,
) -> PageResult:
    """(text, confidence) per OCR line → PageResult with real confidence scores."""
    if blocks_with_conf:
        blocks = [
            Block(type="line", content=text, confidence=conf)
            for text, conf in blocks_with_conf
        ]
        page_conf = sum(b.confidence for b in blocks) / len(blocks)
        raw_text = "\n".join(b.content for b in blocks)
    else:
        blocks = []
        page_conf = 0.0
        raw_text = ""

    return PageResult(
        page_number=page_number,
        document_type=document_type,
        blocks=blocks,
        confidence=round(page_conf, 4),
        raw_text=raw_text,
    )


def _to_page_result(ocr_result, document_type: DocumentType) -> PageResult:
    """OCRPageResult → PageResult（ocr_batch_to_extraction_result 互換ブリッジ）"""
    block = Block(
        type="paragraph",
        content=ocr_result.text,
        confidence=1.0,
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
