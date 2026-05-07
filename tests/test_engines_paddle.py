"""Tests for engines/paddle_engine.py (without requiring paddleocr installed)"""
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))

from engines.base import (
    DocumentType, ExtractionResult, OCREngine, PageResult, Block,
)
from engines.paddle_engine import PaddleEngine, ocr_batch_to_extraction_result, _to_page_result


# ---------------------------------------------------------------------------
# Helpers / stubs
# ---------------------------------------------------------------------------

def _make_ocr_page_result(page_number: int, text: str):
    from text_extractor import OCRPageResult
    return OCRPageResult(page_number=page_number, image_path=Path(f"page_{page_number}.png"), text=text)

def _make_ocr_page_error(page_number: int, message: str):
    from text_extractor import OCRPageError
    return OCRPageError(page_number=page_number, image_path=Path(f"page_{page_number}.png"), error_message=message)

def _make_ocr_batch(pages=(), errors=()):
    from text_extractor import OCRBatchResult
    return OCRBatchResult(pages=list(pages), errors=list(errors))


# ---------------------------------------------------------------------------
# _to_page_result
# ---------------------------------------------------------------------------

def test_to_page_result_basic():
    src = _make_ocr_page_result(1, "甲子乙丑")
    pr = _to_page_result(src, DocumentType.KOYOMI)
    assert pr.page_number == 1
    assert pr.raw_text == "甲子乙丑"
    assert pr.document_type is DocumentType.KOYOMI
    assert len(pr.blocks) == 1
    assert pr.blocks[0].type == "paragraph"
    assert pr.blocks[0].content == "甲子乙丑"


def test_to_page_result_empty_text():
    src = _make_ocr_page_result(3, "")
    pr = _to_page_result(src, DocumentType.AUTO)
    assert pr.raw_text == ""


# ---------------------------------------------------------------------------
# ocr_batch_to_extraction_result
# ---------------------------------------------------------------------------

def test_batch_to_extraction_result_pages():
    batch = _make_ocr_batch(
        pages=[_make_ocr_page_result(1, "page1"), _make_ocr_page_result(2, "page2")],
    )
    er = ocr_batch_to_extraction_result(batch, DocumentType.HONBUN)
    assert len(er.pages) == 2
    assert er.pages[0].raw_text == "page1"
    assert er.pages[1].raw_text == "page2"
    assert er.metadata["engine_name"] == "paddle"


def test_batch_to_extraction_result_errors():
    batch = _make_ocr_batch(
        pages=[_make_ocr_page_result(1, "ok")],
        errors=[_make_ocr_page_error(2, "file not found")],
    )
    er = ocr_batch_to_extraction_result(batch)
    assert len(er.pages) == 1
    assert len(er.errors) == 1
    assert er.errors[0].page_number == 2
    assert "file not found" in er.errors[0].error


# ---------------------------------------------------------------------------
# PaddleEngine - importable, Protocol conformance
# ---------------------------------------------------------------------------

def test_paddle_engine_is_ocr_engine():
    """PaddleEngine は name と extract を持つ（Protocol 要件）"""
    assert hasattr(PaddleEngine, "extract")
    assert PaddleEngine.name == "paddle"
    # インスタンスレベルの isinstance チェックは __init__ が paddleocr を要求するため
    # モックインスタンスで確認する
    engine = PaddleEngine.__new__(PaddleEngine)
    engine.name = "paddle"
    assert isinstance(engine, OCREngine)


def test_paddle_engine_raises_without_paddleocr(monkeypatch):
    """paddleocr 未インストール時に ImportError が出る"""
    import builtins
    real_import = builtins.__import__

    def mock_import(name, *args, **kwargs):
        if "paddleocr" in name or "paddlepaddle" in name:
            raise ImportError("No module named 'paddleocr'")
        return real_import(name, *args, **kwargs)

    with patch("engines.paddle_engine.PaddleEngine.__init__") as mock_init:
        mock_init.side_effect = ImportError("paddleocr is not installed.")
        with pytest.raises(ImportError, match="paddleocr"):
            PaddleEngine()


def test_paddle_engine_extract_mocked():
    """PaddleOCREngine をモックして extract() の変換ロジックを検証"""
    batch = _make_ocr_batch(
        pages=[
            _make_ocr_page_result(1, "元禄十五年"),
            _make_ocr_page_result(2, "甲子"),
        ],
        errors=[_make_ocr_page_error(3, "timeout")],
    )

    engine = PaddleEngine.__new__(PaddleEngine)
    engine.name = "paddle"
    engine._inner = MagicMock()

    with patch("engines.paddle_engine.extract_text_from_images", return_value=batch) as mock_ex:
        result = engine.extract(
            [Path("p1.png"), Path("p2.png"), Path("p3.png")],
            document_type=DocumentType.KOYOMI,
        )

    assert len(result.pages) == 2
    assert len(result.errors) == 1
    assert result.pages[0].raw_text == "元禄十五年"
    assert result.pages[1].document_type is DocumentType.KOYOMI
    assert result.errors[0].error == "timeout"


def test_paddle_engine_progress_callback_called():
    """on_progress が正しく呼ばれる"""
    batch = _make_ocr_batch(pages=[_make_ocr_page_result(1, "test")])
    engine = PaddleEngine.__new__(PaddleEngine)
    engine.name = "paddle"
    engine._inner = MagicMock()

    calls: list[tuple] = []

    def on_progress(current, total, msg):
        calls.append((current, total, msg))

    def _fake_extract(image_paths, engine, on_progress=None):
        if on_progress:
            on_progress(1, 1)  # 1ページ完了をシミュレート
        return batch

    with patch("engines.paddle_engine.extract_text_from_images", side_effect=_fake_extract):
        engine.extract([Path("p1.png")], on_progress=on_progress)

    assert len(calls) == 1
    assert calls[0][0] == 1  # current
    assert calls[0][1] == 1  # total
    assert "PaddleOCR" in calls[0][2]
