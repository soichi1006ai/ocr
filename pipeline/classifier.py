"""
pipeline/classifier.py — 文書種別判定

Claude Sonnet 4.6（軽量・低コスト）でページ画像から koyomi / daichou / honbun を判定する。
キャッシュ: 画像ファイルのパス+mtime をキーに lru_cache で同一ファイルの再判定を防ぐ。
"""
from __future__ import annotations

import hashlib
import json
import logging
import os
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

from engines.base import DocumentType
from engines.claude_engine import _b64_image

logger = logging.getLogger(__name__)

_CLASSIFY_MODEL = "claude-sonnet-4-6"
_CLASSIFY_MAX_TOKENS = 256

# キャッシュ: {cache_key: ClassifyResult}
_cache: dict[str, "ClassifyResult"] = {}

LOW_CONFIDENCE_THRESHOLD = 0.7


@dataclass
class ClassifyResult:
    document_type: DocumentType
    confidence: float
    reason: str
    needs_confirmation: bool  # True if confidence < LOW_CONFIDENCE_THRESHOLD


def classify(
    image_path: Path,
    *,
    api_key: Optional[str] = None,
    use_cache: bool = True,
) -> ClassifyResult:
    """
    画像から文書種別を判定する。

    Parameters
    ----------
    image_path:
        判定対象の画像ファイル
    api_key:
        Anthropic API キー（省略時は環境変数 ANTHROPIC_API_KEY）
    use_cache:
        同一ファイルの再判定をスキップする

    Returns
    -------
    ClassifyResult
        document_type, confidence, reason, needs_confirmation
    """
    resolved = Path(image_path).expanduser().resolve()

    if use_cache:
        cache_key = _cache_key(resolved)
        if cache_key in _cache:
            logger.debug("classifier cache hit: %s", resolved.name)
            return _cache[cache_key]

    result = _call_api(resolved, api_key)

    if use_cache:
        _cache[_cache_key(resolved)] = result

    return result


def clear_cache() -> None:
    _cache.clear()


# ---------------------------------------------------------------------------
# Internal
# ---------------------------------------------------------------------------

def _cache_key(path: Path) -> str:
    stat = path.stat()
    return hashlib.md5(f"{path}:{stat.st_mtime}:{stat.st_size}".encode()).hexdigest()


def _call_api(image_path: Path, api_key: Optional[str]) -> ClassifyResult:
    try:
        import anthropic
    except ImportError as exc:
        raise ImportError("anthropic が未インストールです。pip install anthropic") from exc

    from prompts.loader import load_prompt

    client = anthropic.Anthropic(api_key=api_key or os.environ.get("ANTHROPIC_API_KEY"))
    prompt = load_prompt("classify")
    data, media_type = _b64_image(image_path)

    response = client.messages.create(
        model=_CLASSIFY_MODEL,
        max_tokens=_CLASSIFY_MAX_TOKENS,
        messages=[{
            "role": "user",
            "content": [
                {"type": "image",
                 "source": {"type": "base64", "media_type": media_type, "data": data}},
                {"type": "text", "text": prompt},
            ],
        }],
    )

    raw = response.content[0].text.strip()
    return _parse_classify_response(raw)


def _parse_classify_response(raw: str) -> ClassifyResult:
    cleaned = re.sub(r"```(?:json)?\s*([\s\S]*?)```", r"\1", raw).strip()
    try:
        data = json.loads(cleaned)
        doc_type_str = data.get("document_type", "honbun")
        confidence = float(data.get("confidence", 0.5))
        reason = str(data.get("reason", ""))

        try:
            doc_type = DocumentType(doc_type_str)
        except ValueError:
            doc_type = DocumentType.HONBUN
            confidence = min(confidence, 0.5)

    except (json.JSONDecodeError, KeyError, TypeError):
        logger.warning("classifier: JSON parse failed, defaulting to honbun. raw=%r", raw[:100])
        doc_type = DocumentType.HONBUN
        confidence = 0.3
        reason = "判定失敗（デフォルト）"

    return ClassifyResult(
        document_type=doc_type,
        confidence=confidence,
        reason=reason,
        needs_confirmation=confidence < LOW_CONFIDENCE_THRESHOLD,
    )
