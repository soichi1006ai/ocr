"""Tests for engines/base.py"""
import time
import sys
from pathlib import Path
from unittest.mock import MagicMock

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))

from engines.base import (
    DocumentType, Block, PageResult, PageError, ExtractionResult,
    OCREngine, BaseEngine, ProgressCallback,
)


# --- DocumentType ---

def test_document_type_values():
    assert DocumentType.KOYOMI.value  == "koyomi"
    assert DocumentType.DAICHOU.value == "daichou"
    assert DocumentType.HONBUN.value  == "honbun"
    assert DocumentType.AUTO.value    == "auto"


def test_document_type_str_enum():
    assert DocumentType("koyomi") is DocumentType.KOYOMI


# --- Block ---

def test_block_defaults():
    b = Block(type="paragraph", content="テスト")
    assert b.bbox is None
    assert b.confidence == 1.0


def test_block_with_bbox():
    b = Block(type="table", content=[["a", "b"]], bbox=(0, 0, 100, 50), confidence=0.9)
    assert b.bbox == (0, 0, 100, 50)


# --- PageResult ---

def test_page_result_text_blocks():
    blocks = [
        Block(type="paragraph", content="本文"),
        Block(type="table", content=[["a"]]),
        Block(type="header", content="ヘッダー"),
    ]
    pr = PageResult(page_number=1, document_type=DocumentType.KOYOMI, blocks=blocks, confidence=0.95)
    assert len(pr.text_blocks) == 1
    assert len(pr.table_blocks) == 1


def test_page_result_raw_text_default():
    pr = PageResult(page_number=1, document_type=DocumentType.AUTO, blocks=[], confidence=1.0)
    assert pr.raw_text == ""


# --- ExtractionResult ---

def test_extraction_result_defaults():
    er = ExtractionResult(pages=[])
    assert er.errors == []
    assert er.metadata == {}
    assert not er.has_errors


def test_extraction_result_all_raw_text():
    pages = [
        PageResult(1, DocumentType.HONBUN, [], 1.0, raw_text="page1"),
        PageResult(2, DocumentType.HONBUN, [], 1.0, raw_text="page2"),
    ]
    er = ExtractionResult(pages=pages)
    assert er.all_raw_text() == "page1\n\npage2"


def test_extraction_result_has_errors():
    er = ExtractionResult(pages=[], errors=[PageError(1, "something failed")])
    assert er.has_errors


# --- OCREngine Protocol (runtime_checkable) ---

class MinimalEngine:
    name = "minimal"

    def extract(self, image_paths, document_type=DocumentType.AUTO, on_progress=None):
        return ExtractionResult(pages=[])


def test_ocr_engine_isinstance():
    engine = MinimalEngine()
    assert isinstance(engine, OCREngine)


def test_missing_name_not_protocol():
    class NoName:
        def extract(self, image_paths, document_type=DocumentType.AUTO, on_progress=None):
            return ExtractionResult(pages=[])

    assert not isinstance(NoName(), OCREngine)


def test_missing_extract_not_protocol():
    class NoExtract:
        name = "bad"

    assert not isinstance(NoExtract(), OCREngine)


# --- BaseEngine.retry_with_backoff ---

class ConcreteEngine(BaseEngine):
    name = "test"

    def extract(self, image_paths, document_type=DocumentType.AUTO, on_progress=None):
        return ExtractionResult(pages=[])


def test_retry_success_first_try():
    engine = ConcreteEngine()
    calls = []
    def func():
        calls.append(1)
        return "ok"
    assert engine.retry_with_backoff(func, retries=3, delays=(0,)) == "ok"
    assert len(calls) == 1


def test_retry_success_on_third_try():
    engine = ConcreteEngine()
    calls = []
    def func():
        calls.append(1)
        if len(calls) < 3:
            raise ValueError("transient")
        return "ok"
    result = engine.retry_with_backoff(func, retries=3, delays=(0, 0, 0))
    assert result == "ok"
    assert len(calls) == 3


def test_retry_exhausted_raises():
    engine = ConcreteEngine()
    def func():
        raise RuntimeError("always fails")
    with pytest.raises(RuntimeError, match="always fails"):
        engine.retry_with_backoff(func, retries=2, delays=(0, 0))


def test_retry_non_retriable_raises_immediately():
    engine = ConcreteEngine()
    calls = []
    def func():
        calls.append(1)
        raise TypeError("non-retriable")
    with pytest.raises(TypeError):
        engine.retry_with_backoff(
            func, retries=5, delays=(0,),
            retriable_exceptions=(ValueError,),
        )
    assert len(calls) == 1


def test_retry_timing(monkeypatch):
    """delays が実際に適用されるか確認（monkeypatch でtime.sleep）"""
    engine = ConcreteEngine()
    slept: list[float] = []
    monkeypatch.setattr(time, "sleep", lambda s: slept.append(s))
    calls = []
    def func():
        calls.append(1)
        if len(calls) < 3:
            raise ValueError("retry")
        return "done"
    engine.retry_with_backoff(func, retries=3, delays=(0.5, 1.0, 2.0))
    assert slept == [0.5, 1.0]


# --- BaseEngine is also a valid OCREngine ---

def test_concrete_engine_is_ocr_engine():
    assert isinstance(ConcreteEngine(), OCREngine)
