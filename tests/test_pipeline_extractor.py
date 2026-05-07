"""Tests for pipeline/extractor.py (API calls and PDF conversion mocked)"""
import sys
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest
from PIL import Image

sys.path.insert(0, str(Path(__file__).parent.parent))

from engines.base import DocumentType, ExtractionResult, PageResult, Block, PageError
from pipeline.extractor import Extractor, ExtractionConfig, _build_engine, _validate_page, _apply_correction


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

def _make_page(page_number: int = 1, content: dict | str = "テスト", doc_type=DocumentType.HONBUN) -> PageResult:
    if isinstance(content, dict):
        block = Block(type="paragraph", content=content)
    else:
        block = Block(type="paragraph", content=content)
    return PageResult(page_number=page_number, document_type=doc_type, blocks=[block], confidence=0.9, raw_text=str(content))


def _make_engine_result(pages=None, errors=None):
    return ExtractionResult(
        pages=pages or [],
        errors=errors or [],
        metadata={"engine_name": "mock"},
    )


# ---------------------------------------------------------------------------
# _build_engine
# ---------------------------------------------------------------------------

def test_build_engine_cloud():
    cfg = ExtractionConfig(mode="cloud", api_key="test-key")
    with patch("engines.claude_engine.ClaudeEngine.__init__", return_value=None):
        from engines.claude_engine import ClaudeEngine
        engine = _build_engine(cfg)
        assert hasattr(engine, "extract")


def test_build_engine_local():
    cfg = ExtractionConfig(mode="local")
    with patch("engines.paddle_engine.PaddleEngine.__init__", return_value=None):
        engine = _build_engine(cfg)
        assert hasattr(engine, "extract")


# ---------------------------------------------------------------------------
# _validate_page
# ---------------------------------------------------------------------------

def test_validate_page_empty_blocks():
    """ブロックが空の場合は content={} になり koyomi 検証でエラーが出る（正常動作）"""
    pr = PageResult(1, DocumentType.KOYOMI, [], 1.0)
    errors = _validate_page(pr, DocumentType.KOYOMI)
    # 空コンテンツなので必須フィールドエラーが出るのは期待通り
    assert len(errors) > 0


def test_validate_page_valid_honbun():
    pr = _make_page(content={"raw_text": "江戸時代のテキスト", "paragraphs": []})
    errors = _validate_page(pr, DocumentType.HONBUN)
    assert errors == []


# ---------------------------------------------------------------------------
# _apply_correction
# ---------------------------------------------------------------------------

def test_apply_correction_string_content():
    pr = _make_page(content="甲王乙丑")
    corrected = _apply_correction(pr, apply_kyuujitai=False)
    assert corrected.blocks[0].content == "甲子乙丑"


def test_apply_correction_dict_content():
    pr = _make_page(content={"year": "寛丈元年"})
    corrected = _apply_correction(pr, apply_kyuujitai=False)
    assert "寛文" in corrected.blocks[0].content["year"]


# ---------------------------------------------------------------------------
# Extractor.run — full pipeline mocked
# ---------------------------------------------------------------------------

def _create_dummy_image(path: Path, width=700, height=1000):
    Image.new("RGB", (width, height), (200, 200, 200)).save(path)
    return path


def test_extractor_run_success(tmp_path):
    pdf_path = tmp_path / "test.pdf"
    pdf_path.write_bytes(b"dummy")
    output_dir = tmp_path / "out"

    img_path = tmp_path / "page_001.png"
    _create_dummy_image(img_path)

    engine_mock = MagicMock()
    engine_mock.name = "mock"
    engine_mock.extract.return_value = _make_engine_result(
        pages=[_make_page(1, {"raw_text": "甲子", "paragraphs": []}, DocumentType.HONBUN)]
    )

    progress_calls: list[tuple] = []

    with patch("pipeline.extractor.pdf_to_images", return_value=[img_path]), \
         patch("pipeline.extractor._build_engine", return_value=engine_mock), \
         patch("pipeline.extractor.classify") as mock_classify:

        mock_classify.return_value = MagicMock(document_type=DocumentType.HONBUN)

        cfg = ExtractionConfig(mode="cloud", split_spreads=False, verify_retries=0)
        extractor = Extractor(cfg)
        result = extractor.run(pdf_path, output_dir, on_progress=lambda s, c, t: progress_calls.append((s, c, t)))

    assert len(result.pages) == 1
    assert len(result.errors) == 0
    assert any(s == "ocr" for s, _, _ in progress_calls)


def test_extractor_run_page_error_continues(tmp_path):
    pdf_path = tmp_path / "test.pdf"
    pdf_path.write_bytes(b"dummy")
    output_dir = tmp_path / "out"

    img1 = _create_dummy_image(tmp_path / "page_001.png")
    img2 = _create_dummy_image(tmp_path / "page_002.png")

    engine_mock = MagicMock()
    engine_mock.name = "mock"
    engine_mock.extract.side_effect = [
        _make_engine_result(pages=[_make_page(1)]),
        _make_engine_result(errors=[PageError(2, "API timeout")]),
    ]

    with patch("pipeline.extractor.pdf_to_images", return_value=[img1, img2]), \
         patch("pipeline.extractor._build_engine", return_value=engine_mock), \
         patch("pipeline.extractor.classify", return_value=MagicMock(document_type=DocumentType.HONBUN)):

        cfg = ExtractionConfig(mode="cloud", split_spreads=False, verify_retries=0)
        result = Extractor(cfg).run(pdf_path, output_dir)

    assert len(result.pages) == 1
    assert len(result.errors) == 1
    assert "timeout" in result.errors[0].error
