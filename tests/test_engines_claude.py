"""Tests for engines/claude_engine.py (API calls are mocked)"""
import json
import sys
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock, patch, PropertyMock

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))

from engines.base import DocumentType, ExtractionResult, OCREngine
from engines.claude_engine import (
    ClaudeEngine,
    _doc_type_to_prompt,
    _extract_text_from_response,
    _parse_response,
    _estimate_cost,
    _infer_page_number,
)


# ---------------------------------------------------------------------------
# Helper stubs
# ---------------------------------------------------------------------------

def _make_response(text: str, input_tokens: int = 100, output_tokens: int = 200):
    usage = SimpleNamespace(input_tokens=input_tokens, output_tokens=output_tokens)
    content_block = SimpleNamespace(type="text", text=text)
    return SimpleNamespace(content=[content_block], usage=usage)


def _make_thinking_response(thinking: str, text: str):
    thinking_block = SimpleNamespace(type="thinking", thinking=thinking)
    text_block = SimpleNamespace(type="text", text=text)
    return SimpleNamespace(
        content=[thinking_block, text_block],
        usage=SimpleNamespace(input_tokens=500, output_tokens=300),
    )


# ---------------------------------------------------------------------------
# _doc_type_to_prompt
# ---------------------------------------------------------------------------

def test_doc_type_to_prompt_mapping():
    assert _doc_type_to_prompt(DocumentType.KOYOMI) == "koyomi"
    assert _doc_type_to_prompt(DocumentType.DAICHOU) == "daichou"
    assert _doc_type_to_prompt(DocumentType.HONBUN) == "honbun"
    assert _doc_type_to_prompt(DocumentType.AUTO) == "koyomi"


# ---------------------------------------------------------------------------
# _extract_text_from_response
# ---------------------------------------------------------------------------

def test_extract_text_basic():
    resp = _make_response("甲子乙丑")
    assert _extract_text_from_response(resp) == "甲子乙丑"


def test_extract_text_skips_thinking():
    resp = _make_thinking_response("内部思考...", "出力テキスト")
    assert _extract_text_from_response(resp) == "出力テキスト"


def test_extract_text_multi_text_blocks():
    block1 = SimpleNamespace(type="text", text="block1")
    block2 = SimpleNamespace(type="text", text="block2")
    resp = SimpleNamespace(content=[block1, block2], usage=SimpleNamespace(input_tokens=0, output_tokens=0))
    result = _extract_text_from_response(resp)
    assert "block1" in result
    assert "block2" in result


# ---------------------------------------------------------------------------
# _parse_response
# ---------------------------------------------------------------------------

VALID_JSON = '{"document_type": "koyomi", "year": "元禄15年", "months": []}'

def test_parse_response_valid_json():
    pr = _parse_response(VALID_JSON, 1, DocumentType.KOYOMI)
    assert pr.page_number == 1
    assert pr.confidence == 1.0
    assert pr.blocks[0].type == "paragraph"
    assert isinstance(pr.blocks[0].content, dict)


def test_parse_response_json_in_codeblock():
    raw = f"```json\n{VALID_JSON}\n```"
    pr = _parse_response(raw, 2, DocumentType.KOYOMI)
    assert pr.confidence == 1.0
    assert isinstance(pr.blocks[0].content, dict)


def test_parse_response_invalid_json_fallback():
    pr = _parse_response("これはJSONではない", 1, DocumentType.HONBUN)
    assert pr.confidence == 0.7
    assert isinstance(pr.blocks[0].content, str)


def test_parse_response_raw_text_set():
    pr = _parse_response(VALID_JSON, 1, DocumentType.KOYOMI)
    assert "元禄15年" in pr.raw_text


# ---------------------------------------------------------------------------
# _estimate_cost
# ---------------------------------------------------------------------------

def test_estimate_cost_positive():
    resp = _make_response("x", input_tokens=1000, output_tokens=500)
    cost = _estimate_cost(resp)
    assert cost > 0


def test_estimate_cost_no_usage():
    resp = SimpleNamespace(content=[], usage=None)
    assert _estimate_cost(resp) == 0.0


# ---------------------------------------------------------------------------
# _infer_page_number
# ---------------------------------------------------------------------------

def test_infer_page_number_standard():
    assert _infer_page_number(Path("page_5.png"), fallback=1) == 5


def test_infer_page_number_spread_suffix():
    assert _infer_page_number(Path("page_3_R.png"), fallback=1) == 3
    assert _infer_page_number(Path("page_3_L.png"), fallback=1) == 3


def test_infer_page_number_fallback():
    assert _infer_page_number(Path("image001.png"), fallback=7) == 7


# ---------------------------------------------------------------------------
# ClaudeEngine — Protocol conformance
# ---------------------------------------------------------------------------

def test_claude_engine_is_ocr_engine():
    engine = ClaudeEngine.__new__(ClaudeEngine)
    engine.name = "claude"
    assert isinstance(engine, OCREngine)


def test_claude_engine_raises_without_anthropic(monkeypatch):
    import builtins
    real_import = builtins.__import__

    def mock_import(name, *args, **kwargs):
        if name == "anthropic":
            raise ImportError("No module named 'anthropic'")
        return real_import(name, *args, **kwargs)

    with patch("builtins.__import__", side_effect=mock_import):
        with pytest.raises(Exception):
            ClaudeEngine(api_key="dummy")


# ---------------------------------------------------------------------------
# ClaudeEngine.extract — mocked
# ---------------------------------------------------------------------------

def _make_engine() -> ClaudeEngine:
    engine = ClaudeEngine.__new__(ClaudeEngine)
    engine.name = "claude"
    engine._model = "claude-opus-4-7"
    engine._use_thinking = False
    engine._client = MagicMock()
    return engine


def test_extract_single_page_success():
    engine = _make_engine()
    resp = _make_response(VALID_JSON)
    engine._client.messages.create.return_value = resp

    with patch("engines.claude_engine._b64_image", return_value=("data", "image/jpeg")):
        result = engine.extract([Path("page_1.png")], DocumentType.KOYOMI)

    assert len(result.pages) == 1
    assert len(result.errors) == 0
    assert result.pages[0].confidence == 1.0
    assert result.metadata["engine_name"] == "claude"


def test_extract_progress_callback():
    engine = _make_engine()
    resp = _make_response(VALID_JSON)
    engine._client.messages.create.return_value = resp

    calls: list[tuple] = []

    def on_progress(current, total, msg):
        calls.append((current, total, msg))

    with patch("engines.claude_engine._b64_image", return_value=("data", "image/jpeg")):
        engine.extract([Path("page_1.png"), Path("page_2.png")], on_progress=on_progress)

    assert len(calls) == 2


def test_extract_api_error_goes_to_errors():
    engine = _make_engine()
    engine._client.messages.create.side_effect = RuntimeError("API down")

    with patch("engines.claude_engine._b64_image", return_value=("data", "image/jpeg")):
        result = engine.extract([Path("page_1.png")])

    assert len(result.pages) == 0
    assert len(result.errors) == 1
    assert "API down" in result.errors[0].error


def test_extract_partial_failure():
    engine = _make_engine()
    good_resp = _make_response(VALID_JSON)
    engine._client.messages.create.side_effect = [good_resp, RuntimeError("page 2 failed")]

    with patch("engines.claude_engine._b64_image", return_value=("data", "image/jpeg")):
        result = engine.extract([Path("page_1.png"), Path("page_2.png")])

    assert len(result.pages) == 1
    assert len(result.errors) == 1


def test_extract_thinking_response():
    engine = _make_engine()
    engine._use_thinking = True
    resp = _make_thinking_response("思考中...", VALID_JSON)
    engine._client.messages.create.return_value = resp

    with patch("engines.claude_engine._b64_image", return_value=("data", "image/jpeg")):
        result = engine.extract([Path("page_1.png")], DocumentType.KOYOMI)

    assert len(result.pages) == 1
    assert result.pages[0].confidence == 1.0
