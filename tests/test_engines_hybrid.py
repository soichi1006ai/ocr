"""Tests for engines/hybrid_engine.py"""
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))

from engines.base import (
    Block,
    DocumentType,
    ExtractionResult,
    PageError,
    PageResult,
)
from engines.hybrid_engine import HybridEngine, _merge_pages, DEFAULT_CONFIDENCE_THRESHOLD


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_page(page_number: int = 1, confidence: float = 0.9, block_confidences: list[float] | None = None) -> PageResult:
    block_confidences = block_confidences or [confidence]
    blocks = [Block(type="paragraph", content=f"text_{i}", confidence=c) for i, c in enumerate(block_confidences)]
    return PageResult(
        page_number=page_number,
        document_type=DocumentType.HONBUN,
        blocks=blocks,
        confidence=confidence,
        raw_text="テスト",
    )


def _make_result(pages=None, errors=None, engine_name="mock") -> ExtractionResult:
    return ExtractionResult(
        pages=pages or [],
        errors=errors or [],
        metadata={"engine_name": engine_name},
    )


def _make_hybrid(api_key=None, threshold=DEFAULT_CONFIDENCE_THRESHOLD) -> HybridEngine:
    with patch("engines.paddle_engine.PaddleEngine.__init__", return_value=None), \
         patch("engines.claude_engine.ClaudeEngine.__init__", return_value=None):
        engine = HybridEngine(api_key=api_key, confidence_threshold=threshold)
        engine._paddle = MagicMock()
        engine._claude = MagicMock()
        return engine


# ---------------------------------------------------------------------------
# _merge_pages
# ---------------------------------------------------------------------------

def test_merge_pages_uses_claude_blocks():
    paddle = _make_page(1, confidence=0.7)
    claude = _make_page(1, confidence=0.95)
    merged = _merge_pages(paddle, claude)
    assert merged.blocks == claude.blocks


def test_merge_pages_takes_max_confidence():
    paddle = _make_page(1, confidence=0.7)
    claude = _make_page(1, confidence=0.95)
    merged = _merge_pages(paddle, claude)
    assert merged.confidence == 0.95


def test_merge_pages_max_confidence_paddle_wins():
    paddle = _make_page(1, confidence=0.98)
    claude = _make_page(1, confidence=0.95)
    merged = _merge_pages(paddle, claude)
    assert merged.confidence == 0.98


def test_merge_pages_raw_text_prefers_claude():
    paddle = _make_page(1)
    paddle.raw_text = "paddle text"
    claude = _make_page(1)
    claude.raw_text = "claude text"
    merged = _merge_pages(paddle, claude)
    assert merged.raw_text == "claude text"


def test_merge_pages_raw_text_falls_back_to_paddle():
    paddle = _make_page(1)
    paddle.raw_text = "paddle text"
    claude = _make_page(1)
    claude.raw_text = ""
    merged = _merge_pages(paddle, claude)
    assert merged.raw_text == "paddle text"


def test_merge_pages_preserves_page_number():
    paddle = _make_page(3, confidence=0.7)
    claude = _make_page(3, confidence=0.9)
    merged = _merge_pages(paddle, claude)
    assert merged.page_number == 3


def test_merge_pages_uses_claude_document_type():
    paddle = _make_page(1)
    paddle.document_type = DocumentType.HONBUN
    claude = _make_page(1)
    claude.document_type = DocumentType.KOYOMI
    merged = _merge_pages(paddle, claude)
    assert merged.document_type == DocumentType.KOYOMI


# ---------------------------------------------------------------------------
# HybridEngine.name / Protocol
# ---------------------------------------------------------------------------

def test_hybrid_engine_name():
    engine = _make_hybrid()
    assert engine.name == "hybrid"


def test_hybrid_engine_has_extract():
    engine = _make_hybrid()
    assert callable(engine.extract)


# ---------------------------------------------------------------------------
# _process_page: paddle-only path (all blocks above threshold)
# ---------------------------------------------------------------------------

def test_process_page_paddle_only_when_all_high_conf(tmp_path):
    img = tmp_path / "page.png"
    img.touch()

    engine = _make_hybrid(threshold=0.85)
    high_conf_page = _make_page(1, confidence=0.95, block_confidences=[0.9, 0.95, 0.92])
    engine._paddle.extract.return_value = _make_result(pages=[high_conf_page])

    page, used_claude = engine._process_page(img, 1, DocumentType.HONBUN)

    engine._claude.extract.assert_not_called()
    assert not used_claude
    assert page.confidence == high_conf_page.confidence


def test_process_page_calls_claude_when_low_conf_blocks(tmp_path):
    img = tmp_path / "page.png"
    img.touch()

    engine = _make_hybrid(threshold=0.85)
    low_conf_page = _make_page(1, confidence=0.6, block_confidences=[0.4, 0.95])
    claude_page = _make_page(1, confidence=0.92)

    engine._paddle.extract.return_value = _make_result(pages=[low_conf_page])
    engine._claude.extract.return_value = _make_result(pages=[claude_page])

    page, used_claude = engine._process_page(img, 1, DocumentType.HONBUN)

    engine._claude.extract.assert_called_once()
    assert used_claude
    assert page.blocks == claude_page.blocks


def test_process_page_falls_back_to_paddle_on_claude_error(tmp_path):
    img = tmp_path / "page.png"
    img.touch()

    engine = _make_hybrid(threshold=0.85)
    low_conf_page = _make_page(1, confidence=0.5, block_confidences=[0.3])
    engine._paddle.extract.return_value = _make_result(pages=[low_conf_page])
    engine._claude.extract.return_value = _make_result(
        errors=[PageError(1, "API error")]
    )

    page, used_claude = engine._process_page(img, 1, DocumentType.HONBUN)

    assert used_claude  # Claude was attempted
    assert page == low_conf_page  # fell back to paddle result


def test_process_page_raises_on_paddle_error(tmp_path):
    img = tmp_path / "page.png"
    img.touch()

    engine = _make_hybrid()
    engine._paddle.extract.return_value = _make_result(
        errors=[PageError(1, "PaddleOCR crash")]
    )

    with pytest.raises(RuntimeError, match="Paddle failed"):
        engine._process_page(img, 1, DocumentType.HONBUN)


# ---------------------------------------------------------------------------
# HybridEngine.extract: full flow
# ---------------------------------------------------------------------------

def test_extract_returns_all_pages(tmp_path):
    imgs = [tmp_path / f"p{i}.png" for i in range(3)]
    for img in imgs:
        img.touch()

    engine = _make_hybrid(threshold=0.85)
    pages = [_make_page(i + 1, confidence=0.95) for i in range(3)]
    engine._paddle.extract.side_effect = [_make_result(pages=[p]) for p in pages]

    result = engine.extract(imgs, DocumentType.HONBUN)

    assert len(result.pages) == 3
    assert len(result.errors) == 0


def test_extract_counts_claude_calls(tmp_path):
    img1 = tmp_path / "p1.png"
    img2 = tmp_path / "p2.png"
    img1.touch()
    img2.touch()

    engine = _make_hybrid(threshold=0.85)
    high_conf = _make_page(1, confidence=0.95, block_confidences=[0.95])
    low_conf = _make_page(2, confidence=0.5, block_confidences=[0.4])
    claude_page = _make_page(2, confidence=0.9)

    engine._paddle.extract.side_effect = [
        _make_result(pages=[high_conf]),
        _make_result(pages=[low_conf]),
    ]
    engine._claude.extract.return_value = _make_result(pages=[claude_page])

    result = engine.extract([img1, img2], DocumentType.HONBUN)

    assert result.metadata["claude_calls"] == 1


def test_extract_continues_after_page_error(tmp_path):
    img1 = tmp_path / "p1.png"
    img2 = tmp_path / "p2.png"
    img1.touch()
    img2.touch()

    engine = _make_hybrid()
    good_page = _make_page(1, confidence=0.95)
    engine._paddle.extract.side_effect = [
        _make_result(pages=[good_page]),
        _make_result(errors=[PageError(2, "crash")]),
    ]

    result = engine.extract([img1, img2], DocumentType.HONBUN)

    assert len(result.pages) == 1
    assert len(result.errors) == 1


def test_extract_progress_callback(tmp_path):
    imgs = [tmp_path / f"p{i}.png" for i in range(2)]
    for img in imgs:
        img.touch()

    engine = _make_hybrid(threshold=0.85)
    pages = [_make_page(i + 1, confidence=0.95) for i in range(2)]
    engine._paddle.extract.side_effect = [_make_result(pages=[p]) for p in pages]

    calls: list[tuple] = []
    engine.extract(imgs, DocumentType.HONBUN, on_progress=lambda cur, tot, msg: calls.append((cur, tot, msg)))

    assert len(calls) == 2
    assert calls[0] == (1, 2, "Hybrid OCR page 1/2")
    assert calls[1] == (2, 2, "Hybrid OCR page 2/2")


def test_extract_metadata_fields(tmp_path):
    img = tmp_path / "p.png"
    img.touch()

    engine = _make_hybrid(threshold=0.85)
    engine._paddle.extract.return_value = _make_result(pages=[_make_page(1, confidence=0.95)])

    result = engine.extract([img])

    meta = result.metadata
    assert meta["engine_name"] == "hybrid"
    assert meta["total_pages"] == 1
    assert meta["confidence_threshold"] == 0.85
    assert "claude_calls" in meta


# ---------------------------------------------------------------------------
# Threshold boundary
# ---------------------------------------------------------------------------

def test_threshold_boundary_exactly_at_threshold_is_not_low(tmp_path):
    """confidence == threshold は低信頼ブロックとみなさない（< threshold のみ）"""
    img = tmp_path / "p.png"
    img.touch()

    engine = _make_hybrid(threshold=0.85)
    page = _make_page(1, confidence=0.85, block_confidences=[0.85])
    engine._paddle.extract.return_value = _make_result(pages=[page])

    _, used_claude = engine._process_page(img, 1, DocumentType.HONBUN)
    assert not used_claude


def test_threshold_boundary_just_below_triggers_claude(tmp_path):
    img = tmp_path / "p.png"
    img.touch()

    engine = _make_hybrid(threshold=0.85)
    page = _make_page(1, confidence=0.84, block_confidences=[0.849])
    claude_page = _make_page(1, confidence=0.95)
    engine._paddle.extract.return_value = _make_result(pages=[page])
    engine._claude.extract.return_value = _make_result(pages=[claude_page])

    _, used_claude = engine._process_page(img, 1, DocumentType.HONBUN)
    assert used_claude
