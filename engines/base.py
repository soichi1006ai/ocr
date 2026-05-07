"""
engines/base.py — OCREngine Protocol と共通データクラス

全 OCR エンジンはこの Protocol を実装することでプラガブルに差し替え可能になる。
"""
from __future__ import annotations

import time
import logging
from abc import abstractmethod
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any, Callable, Optional, Protocol, Sequence, runtime_checkable

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# DocumentType
# ---------------------------------------------------------------------------

class DocumentType(str, Enum):
    KOYOMI  = "koyomi"    # 暦表（干支・九星・節気を含む）
    DAICHOU = "daichou"   # 台帳（人名・地名・金額等の表形式）
    HONBUN  = "honbun"    # 本文（汎用縦書きテキスト）
    AUTO    = "auto"      # エンジンが自動判別


# ---------------------------------------------------------------------------
# Block
# ---------------------------------------------------------------------------

@dataclass
class Block:
    """ページ内の1意味単位（段落・表・欄外注記・ヘッダー等）"""
    type: str                                          # "paragraph" | "table" | "marginal_note" | "header"
    content: Any                                       # str | list[list[str]] | dict
    bbox: Optional[tuple[int, int, int, int]] = None   # (x0, y0, x1, y1) in pixels
    confidence: float = 1.0


# ---------------------------------------------------------------------------
# PageResult / PageError
# ---------------------------------------------------------------------------

@dataclass
class PageResult:
    page_number: int
    document_type: DocumentType
    blocks: list[Block]
    confidence: float
    raw_text: str = ""   # 互換用（既存 result.txt フォーマット）

    @property
    def text_blocks(self) -> list[Block]:
        return [b for b in self.blocks if b.type == "paragraph"]

    @property
    def table_blocks(self) -> list[Block]:
        return [b for b in self.blocks if b.type == "table"]


@dataclass
class PageError:
    page_number: int
    error: str
    recoverable: bool = False


# ---------------------------------------------------------------------------
# ExtractionResult
# ---------------------------------------------------------------------------

@dataclass
class ExtractionResult:
    pages: list[PageResult]
    errors: list[PageError] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)
    # metadata キー例: engine_name, total_cost, total_time, confidence_avg

    @property
    def success_pages(self) -> list[PageResult]:
        return self.pages

    @property
    def has_errors(self) -> bool:
        return bool(self.errors)

    def all_raw_text(self) -> str:
        return "\n\n".join(p.raw_text for p in self.pages if p.raw_text)


# ---------------------------------------------------------------------------
# Callback type
# ---------------------------------------------------------------------------

ProgressCallback = Callable[[int, int, str], None]
# (current_page, total_pages, status_message) → None


# ---------------------------------------------------------------------------
# OCREngine Protocol
# ---------------------------------------------------------------------------

@runtime_checkable
class OCREngine(Protocol):
    """全 OCR エンジンの共通インタフェース"""

    name: str  # "claude" | "paddle" | "hybrid" | "ndl"

    def extract(
        self,
        image_paths: Sequence[Path],
        document_type: DocumentType = DocumentType.AUTO,
        on_progress: Optional[ProgressCallback] = None,
    ) -> ExtractionResult:
        """画像群から構造化データを抽出する"""
        ...


# ---------------------------------------------------------------------------
# BaseEngine — retry ロジックを持つ抽象基底
# ---------------------------------------------------------------------------

class BaseEngine:
    """
    OCREngine の共通実装基盤。
    サブクラスは extract() を実装し、retry_with_backoff() でAPI呼び出しをラップする。
    """

    name: str = "base"

    # リトライ設定（サブクラスで上書き可）
    _MAX_RETRIES: int = 3
    _RETRY_DELAYS: tuple[float, ...] = (1.0, 3.0, 10.0)  # 秒

    def retry_with_backoff(
        self,
        func: Callable[[], Any],
        *,
        retries: int | None = None,
        delays: tuple[float, ...] | None = None,
        retriable_exceptions: tuple[type[Exception], ...] = (Exception,),
    ) -> Any:
        """
        func を最大 retries 回リトライする。
        各試行間は delays[i] 秒待機（指数バックオフ相当）。
        retriable_exceptions に含まれない例外は即座に再 raise する。
        """
        max_retries = retries if retries is not None else self._MAX_RETRIES
        retry_delays = delays if delays is not None else self._RETRY_DELAYS

        last_exc: Exception | None = None
        for attempt in range(max_retries + 1):
            try:
                return func()
            except retriable_exceptions as exc:
                last_exc = exc
                if attempt < max_retries:
                    wait = retry_delays[min(attempt, len(retry_delays) - 1)]
                    logger.warning(
                        "[%s] attempt %d/%d failed (%s), retrying in %.1fs",
                        self.name, attempt + 1, max_retries + 1, exc, wait,
                    )
                    time.sleep(wait)
                else:
                    logger.error(
                        "[%s] all %d attempts failed: %s",
                        self.name, max_retries + 1, exc,
                    )

        assert last_exc is not None
        raise last_exc

    @abstractmethod
    def extract(
        self,
        image_paths: Sequence[Path],
        document_type: DocumentType = DocumentType.AUTO,
        on_progress: Optional[ProgressCallback] = None,
    ) -> ExtractionResult:
        raise NotImplementedError
