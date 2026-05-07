"""
engines/claude_engine.py — Claude API OCR エンジン（v2、OCREngine Protocol 実装）

設計方針:
- claude-opus-4-7 + Extended Thinking で最高精度を目指す
- 文書種別ごとにプロンプトを切り替え（koyomi / daichou / honbun）
- ドメイン知識（干支・元号・九星）を毎回プロンプトに注入
- tenacity で最大 3 回リトライ（指数バックオフ）
- 部分失敗でも ExtractionResult を返す（クラッシュしない）
"""
from __future__ import annotations

import base64
import io
import json
import logging
import os
import re
from pathlib import Path
from typing import Any, Optional, Sequence

from engines.base import (
    BaseEngine,
    Block,
    DocumentType,
    ExtractionResult,
    PageError,
    PageResult,
    ProgressCallback,
)
from prompts.loader import load_prompt

logger = logging.getLogger(__name__)

MODEL = "claude-opus-4-7"
MAX_TOKENS = 8192
THINKING_BUDGET = 4000

_LIMIT_BYTES = 4 * 1024 * 1024  # 4MB (5MB 上限に対する安全マージン)


class ClaudeEngineError(Exception):
    pass


class ClaudeEngine(BaseEngine):
    """
    Claude API（Vision + Extended Thinking）OCR エンジン。

    Parameters
    ----------
    api_key:
        Anthropic API キー。省略時は ANTHROPIC_API_KEY 環境変数を使用。
    model:
        使用モデル。デフォルト: claude-opus-4-7
    use_thinking:
        Extended Thinking を有効にする（デフォルト: True）。
    """

    name = "claude"

    def __init__(
        self,
        api_key: Optional[str] = None,
        model: str = MODEL,
        use_thinking: bool = True,
    ) -> None:
        try:
            import anthropic
        except ImportError as exc:
            raise ClaudeEngineError(
                "anthropic が未インストールです。pip install anthropic を実行してください。"
            ) from exc

        self._client = anthropic.Anthropic(
            api_key=api_key or os.environ.get("ANTHROPIC_API_KEY")
        )
        self._model = model
        self._use_thinking = use_thinking

    def extract(
        self,
        image_paths: Sequence[Path],
        document_type: DocumentType = DocumentType.AUTO,
        on_progress: Optional[ProgressCallback] = None,
    ) -> ExtractionResult:
        total = len(image_paths)
        pages: list[PageResult] = []
        errors: list[PageError] = []
        total_cost = 0.0

        for index, image_path in enumerate(image_paths, start=1):
            resolved = Path(image_path).expanduser().resolve()
            page_number = _infer_page_number(resolved, fallback=index)

            if on_progress:
                on_progress(index, total, f"Claude OCR page {index}/{total}")

            try:
                page_result, cost = self._ocr_page(resolved, page_number, document_type)
                pages.append(page_result)
                total_cost += cost
            except Exception as exc:
                logger.error("page %d OCR failed: %s", page_number, exc)
                errors.append(PageError(page_number, str(exc), recoverable=False))

        return ExtractionResult(
            pages=pages,
            errors=errors,
            metadata={
                "engine_name": self.name,
                "model": self._model,
                "total_cost_usd": round(total_cost, 4),
            },
        )

    def _ocr_page(
        self,
        image_path: Path,
        page_number: int,
        document_type: DocumentType,
    ) -> tuple[PageResult, float]:
        """1ページを OCR してPageResult とコスト概算を返す"""
        from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception_type
        import anthropic

        prompt_name = _doc_type_to_prompt(document_type)
        prompt = load_prompt(prompt_name)
        data, media_type = _b64_image(image_path)

        @retry(
            stop=stop_after_attempt(3),
            wait=wait_exponential(multiplier=1, min=2, max=30),
            retry=retry_if_exception_type((anthropic.APIConnectionError, anthropic.RateLimitError)),
            reraise=True,
        )
        def _call() -> Any:
            kwargs: dict[str, Any] = {
                "model": self._model,
                "max_tokens": MAX_TOKENS,
                "messages": [{
                    "role": "user",
                    "content": [
                        {"type": "image",
                         "source": {"type": "base64",
                                    "media_type": media_type,
                                    "data": data}},
                        {"type": "text", "text": prompt},
                    ],
                }],
            }
            if self._use_thinking:
                kwargs["thinking"] = {
                    "type": "enabled",
                    "budget_tokens": THINKING_BUDGET,
                }
            return self._client.messages.create(**kwargs)

        response = _call()
        raw_text = _extract_text_from_response(response)
        cost = _estimate_cost(response)

        page_result = _parse_response(raw_text, page_number, document_type)
        return page_result, cost


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _doc_type_to_prompt(doc_type: DocumentType) -> str:
    mapping = {
        DocumentType.KOYOMI:  "koyomi",
        DocumentType.DAICHOU: "daichou",
        DocumentType.HONBUN:  "honbun",
        DocumentType.AUTO:    "koyomi",  # AUTO時は暦表を試みる
    }
    return mapping[doc_type]


def _extract_text_from_response(response: Any) -> str:
    """レスポンスから text ブロックだけ結合して返す（thinking ブロックを除外）"""
    parts: list[str] = []
    for block in response.content:
        if getattr(block, "type", None) == "text":
            parts.append(block.text)
    return "\n".join(parts).strip()


def _parse_response(raw: str, page_number: int, doc_type: DocumentType) -> PageResult:
    """生レスポンスを PageResult に変換"""
    # コードブロック除去
    cleaned = re.sub(r"```(?:json)?\s*([\s\S]*?)```", r"\1", raw).strip()

    structured: dict | None = None
    try:
        structured = json.loads(cleaned)
    except json.JSONDecodeError:
        pass

    if structured:
        block = Block(type="paragraph", content=structured, confidence=1.0)
        raw_text = json.dumps(structured, ensure_ascii=False)
    else:
        block = Block(type="paragraph", content=raw, confidence=0.7)
        raw_text = raw

    return PageResult(
        page_number=page_number,
        document_type=doc_type,
        blocks=[block],
        confidence=1.0 if structured else 0.7,
        raw_text=raw_text,
    )


def _estimate_cost(response: Any) -> float:
    """claude-opus-4-7 の入出力トークンからコストを概算（USD）"""
    usage = getattr(response, "usage", None)
    if usage is None:
        return 0.0
    input_tokens = getattr(usage, "input_tokens", 0)
    output_tokens = getattr(usage, "output_tokens", 0)
    # claude-opus-4-7: $15/1M input, $75/1M output (2025年時点概算)
    return (input_tokens * 15 + output_tokens * 75) / 1_000_000


def _b64_image(path: Path) -> tuple[str, str]:
    """画像を base64 エンコード。4MB超の場合は解像度を保ちつつ JPEG 変換。"""
    from PIL import Image

    raw = path.read_bytes()
    if len(raw) <= _LIMIT_BYTES:
        media = {
            ".png": "image/png",
            ".jpg": "image/jpeg",
            ".jpeg": "image/jpeg",
            ".tiff": "image/tiff",
            ".tif": "image/tiff",
        }.get(path.suffix.lower(), "image/png")
        return base64.standard_b64encode(raw).decode(), media

    img = Image.open(path).convert("RGB")
    buf = io.BytesIO()
    img.save(buf, format="JPEG", quality=88)
    if len(buf.getvalue()) <= _LIMIT_BYTES:
        return base64.standard_b64encode(buf.getvalue()).decode(), "image/jpeg"

    w, h = img.size
    for max_side in (4000, 3000, 2000):
        scale = min(max_side / max(w, h), 1.0)
        resized = img.resize((int(w * scale), int(h * scale)), Image.LANCZOS)
        buf = io.BytesIO()
        resized.save(buf, format="JPEG", quality=88)
        if len(buf.getvalue()) <= _LIMIT_BYTES:
            break

    return base64.standard_b64encode(buf.getvalue()).decode(), "image/jpeg"


def _infer_page_number(image_path: Path, *, fallback: int) -> int:
    stem = image_path.stem
    if stem.startswith("page_"):
        suffix = stem.removeprefix("page_")
        for side in ("_R", "_L"):
            if suffix.endswith(side):
                suffix = suffix[: -len(side)]
                break
        if suffix.isdigit():
            return int(suffix)
    return fallback
