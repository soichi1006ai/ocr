"""Tests for pipeline/classifier.py (API calls are mocked)"""
import sys
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch, MagicMock

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))

from engines.base import DocumentType
from pipeline.classifier import (
    ClassifyResult,
    classify,
    clear_cache,
    _parse_classify_response,
    LOW_CONFIDENCE_THRESHOLD,
)


@pytest.fixture(autouse=True)
def reset_cache():
    clear_cache()
    yield
    clear_cache()


# ---------------------------------------------------------------------------
# _parse_classify_response
# ---------------------------------------------------------------------------

def test_parse_koyomi():
    raw = '{"document_type": "koyomi", "confidence": 0.95, "reason": "格子状の干支・九星"}'
    result = _parse_classify_response(raw)
    assert result.document_type is DocumentType.KOYOMI
    assert result.confidence == 0.95
    assert not result.needs_confirmation


def test_parse_daichou():
    raw = '{"document_type": "daichou", "confidence": 0.85, "reason": "台帳形式"}'
    result = _parse_classify_response(raw)
    assert result.document_type is DocumentType.DAICHOU


def test_parse_honbun():
    raw = '{"document_type": "honbun", "confidence": 0.7, "reason": "縦書き本文"}'
    result = _parse_classify_response(raw)
    assert result.document_type is DocumentType.HONBUN
    assert not result.needs_confirmation


def test_parse_low_confidence_needs_confirmation():
    raw = '{"document_type": "koyomi", "confidence": 0.55, "reason": "不明瞭"}'
    result = _parse_classify_response(raw)
    assert result.needs_confirmation
    assert result.confidence < LOW_CONFIDENCE_THRESHOLD


def test_parse_json_in_codeblock():
    raw = '```json\n{"document_type": "koyomi", "confidence": 0.9, "reason": "ok"}\n```'
    result = _parse_classify_response(raw)
    assert result.document_type is DocumentType.KOYOMI


def test_parse_invalid_doc_type_falls_back():
    raw = '{"document_type": "unknown_type", "confidence": 0.8, "reason": "?"}'
    result = _parse_classify_response(raw)
    assert result.document_type is DocumentType.HONBUN
    assert result.confidence <= 0.5


def test_parse_broken_json_falls_back():
    result = _parse_classify_response("これはJSONではない")
    assert result.document_type is DocumentType.HONBUN
    assert result.confidence == 0.3
    assert result.needs_confirmation


# ---------------------------------------------------------------------------
# classify() — mocked API
# ---------------------------------------------------------------------------

def _make_api_response(text: str):
    block = SimpleNamespace(text=text)
    return SimpleNamespace(content=[block])


def test_classify_koyomi_mock(tmp_path):
    img = tmp_path / "page_1.png"
    img.write_bytes(b"dummy")

    api_resp = _make_api_response('{"document_type": "koyomi", "confidence": 0.95, "reason": "暦表"}')

    with patch("pipeline.classifier._call_api", return_value=_parse_classify_response(api_resp.content[0].text)):
        result = classify(img)

    assert result.document_type is DocumentType.KOYOMI


def test_classify_uses_cache(tmp_path):
    img = tmp_path / "page_1.png"
    img.write_bytes(b"dummy")

    call_count = [0]
    def fake_call(image_path, api_key):
        call_count[0] += 1
        return ClassifyResult(DocumentType.KOYOMI, 0.9, "cached", False)

    with patch("pipeline.classifier._call_api", side_effect=fake_call):
        classify(img)
        classify(img)  # 2回目はキャッシュが効く

    assert call_count[0] == 1


def test_classify_cache_disabled(tmp_path):
    img = tmp_path / "page_1.png"
    img.write_bytes(b"dummy")

    call_count = [0]
    def fake_call(image_path, api_key):
        call_count[0] += 1
        return ClassifyResult(DocumentType.KOYOMI, 0.9, "no cache", False)

    with patch("pipeline.classifier._call_api", side_effect=fake_call):
        classify(img, use_cache=False)
        classify(img, use_cache=False)

    assert call_count[0] == 2


def test_classify_result_fields(tmp_path):
    img = tmp_path / "page_1.png"
    img.write_bytes(b"dummy")

    expected = ClassifyResult(DocumentType.DAICHOU, 0.88, "台帳形式", False)
    with patch("pipeline.classifier._call_api", return_value=expected):
        result = classify(img)

    assert result.document_type is DocumentType.DAICHOU
    assert result.confidence == 0.88
    assert result.reason == "台帳形式"
    assert not result.needs_confirmation
