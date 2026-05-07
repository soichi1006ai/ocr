"""Tests for engines/paddle_engine.py (without requiring paddleocr installed)"""
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))

from engines.base import (
    DocumentType, ExtractionResult, OCREngine, PageResult, Block,
)
from engines.paddle_engine import (
    PaddleEngine, ocr_batch_to_extraction_result, _to_page_result, _blocks_to_page_result,
)


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
    """extract_blocks_from_image をモックして extract() の変換ロジックを検証"""
    engine = PaddleEngine.__new__(PaddleEngine)
    engine.name = "paddle"
    engine._inner = MagicMock()

    page1_blocks = [("元禄十五年", 0.95), ("甲子", 0.88)]
    page2_blocks = [("乙丑", 0.90)]

    def _fake_blocks(img_path, engine=None):
        name = Path(img_path).name
        if name == "page_001.png":
            return page1_blocks
        if name == "page_002.png":
            return page2_blocks
        raise RuntimeError("timeout")

    with patch("engines.paddle_engine.extract_blocks_from_image", side_effect=_fake_blocks):
        result = engine.extract(
            [Path("page_001.png"), Path("page_002.png"), Path("page_003.png")],
            document_type=DocumentType.KOYOMI,
        )

    assert len(result.pages) == 2
    assert len(result.errors) == 1
    assert "元禄十五年" in result.pages[0].raw_text
    assert result.pages[0].document_type is DocumentType.KOYOMI
    assert result.pages[0].blocks[0].confidence == 0.95
    assert result.pages[0].blocks[1].confidence == 0.88
    assert "timeout" in result.errors[0].error


def test_paddle_engine_progress_callback_called():
    """on_progress が正しく呼ばれる"""
    engine = PaddleEngine.__new__(PaddleEngine)
    engine.name = "paddle"
    engine._inner = MagicMock()

    calls: list[tuple] = []

    def on_progress(current, total, msg):
        calls.append((current, total, msg))

    with patch("engines.paddle_engine.extract_blocks_from_image", return_value=[("test", 0.9)]):
        engine.extract([Path("page_001.png")], on_progress=on_progress)

    assert len(calls) == 1
    assert calls[0][0] == 1
    assert calls[0][1] == 1
    assert "PaddleOCR" in calls[0][2]


# ---------------------------------------------------------------------------
# _extract_lines_with_scores (text_extractor)
# ---------------------------------------------------------------------------

def test_extract_lines_with_scores_normal():
    from text_extractor import _extract_lines_with_scores
    raw = [[
        [[[0, 0], [100, 0], [100, 20], [0, 20]], ["甲子", 0.93]],
        [[[0, 25], [100, 25], [100, 45], [0, 45]], ["乙丑", 0.87]],
    ]]
    lines = _extract_lines_with_scores(raw)
    assert len(lines) == 2
    assert lines[0] == ("甲子", 0.93)
    assert lines[1] == ("乙丑", 0.87)


def test_extract_lines_with_scores_clamps_confidence():
    from text_extractor import _extract_lines_with_scores
    raw = [[
        [[[0, 0], [1, 0], [1, 1], [0, 1]], ["甲子", 1.5]],
        [[[0, 5], [1, 5], [1, 6], [0, 6]], ["乙丑", -0.1]],
    ]]
    lines = _extract_lines_with_scores(raw)
    for _, conf in lines:
        assert 0.0 <= conf <= 1.0


def test_extract_lines_with_scores_empty():
    from text_extractor import _extract_lines_with_scores
    assert _extract_lines_with_scores(None) == []
    assert _extract_lines_with_scores([]) == []
    assert _extract_lines_with_scores([[]]) == []


def test_extract_lines_with_scores_missing_confidence_defaults_to_1():
    from text_extractor import _extract_lines_with_scores
    # candidate は [text] のみ（confidence なし）
    raw = [[
        [[[0, 0], [1, 0], [1, 1], [0, 1]], ["甲子"]],
    ]]
    lines = _extract_lines_with_scores(raw)
    assert lines[0][1] == 1.0


# ---------------------------------------------------------------------------
# _blocks_to_page_result
# ---------------------------------------------------------------------------

def test_blocks_to_page_result_confidence_mean():
    pr = _blocks_to_page_result(1, [("甲子", 0.8), ("乙丑", 0.9)], DocumentType.KOYOMI)
    assert abs(pr.confidence - 0.85) < 1e-4


def test_blocks_to_page_result_raw_text_joined():
    pr = _blocks_to_page_result(1, [("甲子", 0.9), ("乙丑", 0.8)], DocumentType.KOYOMI)
    assert pr.raw_text == "甲子\n乙丑"


def test_blocks_to_page_result_empty_blocks():
    pr = _blocks_to_page_result(1, [], DocumentType.KOYOMI)
    assert pr.blocks == []
    assert pr.confidence == 0.0
    assert pr.raw_text == ""


def test_blocks_to_page_result_block_type_is_line():
    pr = _blocks_to_page_result(1, [("甲子", 0.95)], DocumentType.KOYOMI)
    assert pr.blocks[0].type == "line"
    assert pr.blocks[0].content == "甲子"
    assert pr.blocks[0].confidence == 0.95


def test_blocks_to_page_result_confidence_clamped():
    pr = _blocks_to_page_result(1, [("甲子", 1.0), ("乙丑", 0.5)], DocumentType.KOYOMI)
    assert 0.0 <= pr.confidence <= 1.0
