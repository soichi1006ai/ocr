"""
pipeline/extractor.py — メインオーケストレーター（T4.1 + T4.5）

フロー:
  PDF → PNG → Splitter → Classifier → Preprocessor
      → Engine → Validator → (NG→ verify retry) → Corrector → ExtractionResult
"""
from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, Optional

from engines.base import DocumentType, ExtractionResult, PageError, PageResult
from pipeline.classifier import classify, ClassifyResult
from pipeline.corrector import correct_structured, correct_text
from pipeline.preprocessor import pdf_to_images, preprocess
from pipeline.splitter import is_spread_image, split_spread_pages
from pipeline.validator import ValidationError, validate_result

logger = logging.getLogger(__name__)

MAX_VERIFY_RETRIES = 2

ProgressCallback = Callable[[str, int, int], None]
# (stage_name, current, total) → None


@dataclass
class ExtractionConfig:
    mode: str = "cloud"          # "cloud" | "local" | "hybrid"
    document_type: DocumentType = DocumentType.AUTO
    auto_classify: bool = True   # AUTO時にClassifierを使う
    split_spreads: bool = True   # 見開き自動分割
    apply_kyuujitai: bool = False
    api_key: Optional[str] = None
    dpi: int = 300
    verify_retries: int = MAX_VERIFY_RETRIES


class Extractor:
    """OCR パイプラインのメインオーケストレーター"""

    def __init__(self, config: Optional[ExtractionConfig] = None) -> None:
        self._config = config or ExtractionConfig()

    def run(
        self,
        pdf_path: Path,
        output_dir: Path,
        *,
        on_progress: Optional[ProgressCallback] = None,
    ) -> ExtractionResult:
        """
        PDF を OCR 処理して ExtractionResult を返す。

        Parameters
        ----------
        pdf_path:
            入力 PDF ファイル
        output_dir:
            中間ファイル・出力ファイルの保存先
        on_progress:
            進捗コールバック（stage, current, total）
        """
        cfg = self._config

        def progress(stage: str, current: int, total: int) -> None:
            logger.info("[%s] %d/%d", stage, current, total)
            if on_progress:
                on_progress(stage, current, total)

        # ── 1. PDF → PNG ──────────────────────────────────
        progress("pdf_convert", 0, 1)
        image_dir = output_dir / "images"
        image_paths = pdf_to_images(pdf_path, image_dir, dpi=cfg.dpi)
        progress("pdf_convert", 1, 1)

        # ── 2. 見開き分割 ─────────────────────────────────
        if cfg.split_spreads:
            split_dir = output_dir / "split"
            image_paths = split_spread_pages(image_paths, split_dir)

        total_pages = len(image_paths)

        # ── 3. エンジン選択 ───────────────────────────────
        engine = _build_engine(cfg)

        # ── 4. ページ別処理 ───────────────────────────────
        all_pages: list[PageResult] = []
        all_errors: list[PageError] = []

        for idx, img_path in enumerate(image_paths, start=1):
            progress("ocr", idx, total_pages)

            try:
                page_result = self._process_page(img_path, idx, cfg, engine)
                all_pages.append(page_result)
            except Exception as exc:
                logger.error("page %d failed: %s", idx, exc)
                all_errors.append(PageError(idx, str(exc)))

        return ExtractionResult(
            pages=all_pages,
            errors=all_errors,
            metadata={
                "engine_name": engine.name,
                "mode": cfg.mode,
                "total_pages": total_pages,
            },
        )

    def _process_page(
        self,
        img_path: Path,
        page_number: int,
        cfg: ExtractionConfig,
        engine,
    ) -> PageResult:
        """1ページを処理: 分類 → 前処理 → OCR → 検証＆再試行 → 補正"""

        # 文書種別判定
        doc_type = cfg.document_type
        if doc_type is DocumentType.AUTO and cfg.auto_classify:
            try:
                classify_result = classify(img_path, api_key=cfg.api_key)
                doc_type = classify_result.document_type
            except Exception as exc:
                logger.warning("classify failed for page %d: %s", page_number, exc)
                doc_type = DocumentType.HONBUN

        # 前処理
        preprocessed = preprocess(img_path, mode=cfg.mode)

        # OCR
        er = engine.extract([preprocessed], document_type=doc_type)
        if er.errors:
            raise RuntimeError(er.errors[0].error)

        page_result = er.pages[0]

        # 検証 & 再抽出（verify retry）
        page_result = self._validate_and_retry(
            page_result, img_path, doc_type, cfg, engine
        )

        # 辞書補正
        page_result = _apply_correction(page_result, apply_kyuujitai=cfg.apply_kyuujitai)

        return page_result

    def _validate_and_retry(
        self,
        page_result: PageResult,
        img_path: Path,
        doc_type: DocumentType,
        cfg: ExtractionConfig,
        engine,
    ) -> PageResult:
        """バリデーション失敗時に verify プロンプトで再抽出する（最大 cfg.verify_retries 回）"""
        if cfg.verify_retries <= 0:
            return page_result

        errors = _validate_page(page_result, doc_type)
        if not errors:
            return page_result

        for attempt in range(cfg.verify_retries):
            logger.info(
                "page %d validation failed (%d errors), retry %d/%d",
                page_result.page_number, len(errors), attempt + 1, cfg.verify_retries,
            )
            try:
                page_result = self._verify_retry(page_result, img_path, doc_type, errors, engine)
            except Exception as exc:
                logger.warning("verify retry failed: %s", exc)
                break

            errors = _validate_page(page_result, doc_type)
            if not errors:
                break

        return page_result

    def _verify_retry(
        self,
        page_result: PageResult,
        img_path: Path,
        doc_type: DocumentType,
        errors: list[ValidationError],
        engine,
    ) -> PageResult:
        """verify_koyomi プロンプトを使って再抽出する"""
        from prompts.loader import load_prompt

        prev_json = page_result.raw_text
        error_text = "\n".join(f"- {e.field}: {e.message}" for e in errors)
        prompt_name = f"verify_{doc_type.value}" if doc_type != DocumentType.AUTO else "verify_koyomi"

        try:
            load_prompt(prompt_name)  # テンプレートが存在するか確認
        except FileNotFoundError:
            prompt_name = "verify_koyomi"

        from engines.claude_engine import ClaudeEngine, _b64_image, _parse_response

        data, media_type = _b64_image(img_path)
        prompt = load_prompt(prompt_name, PREVIOUS_JSON=prev_json, VALIDATION_ERRORS=error_text)

        engine._client.messages.create  # duck-type check
        response = engine._client.messages.create(
            model=engine._model,
            max_tokens=8192,
            messages=[{
                "role": "user",
                "content": [
                    {"type": "image",
                     "source": {"type": "base64", "media_type": media_type, "data": data}},
                    {"type": "text", "text": prompt},
                ],
            }],
        )
        from engines.claude_engine import _extract_text_from_response
        raw = _extract_text_from_response(response)
        return _parse_response(raw, page_result.page_number, doc_type)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _build_engine(cfg: ExtractionConfig):
    if cfg.mode == "local":
        from engines.paddle_engine import PaddleEngine
        return PaddleEngine()
    else:
        from engines.claude_engine import ClaudeEngine
        return ClaudeEngine(api_key=cfg.api_key)


def _validate_page(page_result: PageResult, doc_type: DocumentType) -> list[ValidationError]:
    content = page_result.blocks[0].content if page_result.blocks else {}
    if isinstance(content, dict):
        return validate_result(content, doc_type.value)
    return []


def _apply_correction(page_result: PageResult, *, apply_kyuujitai: bool) -> PageResult:
    for block in page_result.blocks:
        if isinstance(block.content, str):
            diff = correct_text(block.content, apply_kyuujitai=apply_kyuujitai)
            block.content = diff.corrected
        elif isinstance(block.content, dict):
            block.content = correct_structured(block.content, apply_kyuujitai=apply_kyuujitai)
    return page_result
