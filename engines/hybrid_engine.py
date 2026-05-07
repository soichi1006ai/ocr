"""
engines/hybrid_engine.py — ハイブリッド OCR エンジン（T5.1 + T5.2）

フロー:
  1. PaddleEngine で全体を一次抽出（高速・無料）
  2. ブロックの confidence を評価
  3. 低信頼ブロック（< threshold）のみ ClaudeEngine に再質問
  4. 結果をマージして ExtractionResult を返す

コスト削減目標: Claude 単独の 1/5 以下
"""
from __future__ import annotations

import logging
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

logger = logging.getLogger(__name__)

DEFAULT_CONFIDENCE_THRESHOLD = 0.85


class HybridEngine(BaseEngine):
    """
    PaddleOCR + Claude API のハイブリッドエンジン。

    Parameters
    ----------
    api_key:
        Anthropic API キー（Claude 側）
    confidence_threshold:
        これ未満の confidence を持つブロックを Claude に再質問する
    """

    name = "hybrid"

    def __init__(
        self,
        api_key: Optional[str] = None,
        confidence_threshold: float = DEFAULT_CONFIDENCE_THRESHOLD,
    ) -> None:
        from engines.paddle_engine import PaddleEngine
        from engines.claude_engine import ClaudeEngine

        self._paddle = PaddleEngine()
        self._claude = ClaudeEngine(api_key=api_key)
        self._threshold = confidence_threshold

    def extract(
        self,
        image_paths: Sequence[Path],
        document_type: DocumentType = DocumentType.AUTO,
        on_progress: Optional[ProgressCallback] = None,
    ) -> ExtractionResult:
        total = len(image_paths)
        pages: list[PageResult] = []
        errors: list[PageError] = []
        low_conf_count = 0
        claude_calls = 0

        for idx, img_path in enumerate(image_paths, start=1):
            if on_progress:
                on_progress(idx, total, f"Hybrid OCR page {idx}/{total}")

            try:
                page_result, used_claude = self._process_page(img_path, idx, document_type)
                pages.append(page_result)
                if used_claude:
                    claude_calls += 1
            except Exception as exc:
                logger.error("hybrid page %d failed: %s", idx, exc)
                errors.append(PageError(idx, str(exc)))

        return ExtractionResult(
            pages=pages,
            errors=errors,
            metadata={
                "engine_name": self.name,
                "total_pages": total,
                "claude_calls": claude_calls,
                "low_confidence_pages": low_conf_count,
                "confidence_threshold": self._threshold,
            },
        )

    def _process_page(
        self,
        img_path: Path,
        page_number: int,
        document_type: DocumentType,
    ) -> tuple[PageResult, bool]:
        """
        1ページを処理する。
        Returns (PageResult, used_claude_flag)
        """
        # Step 1: Paddle で一次抽出
        paddle_result = self._paddle.extract([img_path], document_type=document_type)

        if paddle_result.errors:
            raise RuntimeError(f"Paddle failed: {paddle_result.errors[0].error}")

        page = paddle_result.pages[0]

        # Step 2: confidence チェック
        low_conf_blocks = [b for b in page.blocks if b.confidence < self._threshold]

        if not low_conf_blocks:
            logger.debug("page %d: all blocks above threshold (paddle only)", page_number)
            return page, False

        logger.info(
            "page %d: %d/%d blocks below threshold %.2f → sending to Claude",
            page_number, len(low_conf_blocks), len(page.blocks), self._threshold,
        )

        # Step 3: Claude で全体を再抽出（低信頼ブロックが多い場合）
        claude_result = self._claude.extract([img_path], document_type=document_type)
        if claude_result.errors:
            logger.warning("Claude fallback failed for page %d, using Paddle result", page_number)
            return page, True

        claude_page = claude_result.pages[0]

        # Step 4: マージ（Claude の結果で低信頼ブロックを置き換え）
        merged = _merge_pages(page, claude_page)
        return merged, True


# ---------------------------------------------------------------------------
# Helper
# ---------------------------------------------------------------------------

def _merge_pages(paddle_page: PageResult, claude_page: PageResult) -> PageResult:
    """
    Paddle の高信頼ブロックと Claude の結果をマージする。
    現実装では Claude の PageResult をそのまま使い、
    Paddle のメタ情報（confidence スコア）だけを引き継ぐ。
    """
    return PageResult(
        page_number=paddle_page.page_number,
        document_type=claude_page.document_type,
        blocks=claude_page.blocks,
        confidence=max(paddle_page.confidence, claude_page.confidence),
        raw_text=claude_page.raw_text or paddle_page.raw_text,
    )
