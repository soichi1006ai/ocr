from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Callable, List, Optional, Protocol, Sequence
import unicodedata

from image_preprocessor import (
    ImagePreprocessingError,
    preprocess_image_for_ocr,
    split_image_for_vertical_ocr,
)


class OCREngine(Protocol):
    def ocr(self, img: str, cls: bool = True):
        ...


ProgressCallback = Callable[[int, int], None]
ErrorCallback = Callable[[int, Path, Exception], None]


@dataclass(frozen=True)
class OCRPageResult:
    page_number: int
    image_path: Path
    text: str


@dataclass(frozen=True)
class OCRPageError:
    page_number: int
    image_path: Path
    error_message: str


@dataclass(frozen=True)
class OCRBatchResult:
    pages: list[OCRPageResult]
    errors: list[OCRPageError]


class OCRProcessingError(Exception):
    """Raised when OCR processing cannot continue."""


class PaddleOCREngine:
    """OCR engine backed by PaddleOCR 2.7.x. Supports Japanese + English."""

    def __init__(self, lang: str = "japan", use_angle_cls: bool = True) -> None:
        try:
            from paddleocr import PaddleOCR
        except ImportError as exc:
            raise OCRProcessingError(
                "paddleocr is not installed. Run: pip install paddleocr==2.7.3"
            ) from exc

        self._engine = PaddleOCR(lang=lang, use_angle_cls=use_angle_cls, show_log=False)

    def ocr(self, img: str, cls: bool = True):
        return self._engine.ocr(img, cls=cls)


def extract_text_from_image(
    image_path: str | Path,
    *,
    engine: Optional[OCREngine] = None,
) -> str:
    path = Path(image_path).expanduser().resolve()
    if not path.exists():
        raise FileNotFoundError(f"Image file not found: {path}")

    ocr_engine = engine or PaddleOCREngine()
    segment_paths: list[Path] = []
    try:
        segment_paths = split_image_for_vertical_ocr(path)
        texts: list[str] = []
        for segment_path in segment_paths:
            raw_result = ocr_engine.ocr(str(segment_path), cls=True)
            text = _normalize_ocr_text(_flatten_ocr_result(raw_result))
            if text:
                texts.append(text)
    except ImagePreprocessingError as exc:
        raise OCRProcessingError(str(exc)) from exc
    except Exception as exc:
        raise OCRProcessingError(f"OCR failed for image: {path}") from exc
    finally:
        for segment_path in segment_paths:
            segment_path.unlink(missing_ok=True)

    return "\n".join(part for part in texts if part)


def extract_text_from_images(
    image_paths: Sequence[str | Path],
    *,
    engine: Optional[OCREngine] = None,
    on_progress: Optional[ProgressCallback] = None,
    on_error: Optional[ErrorCallback] = None,
) -> OCRBatchResult:
    if not image_paths:
        return OCRBatchResult(pages=[], errors=[])

    ocr_engine = engine or PaddleOCREngine()
    total = len(image_paths)
    results: List[OCRPageResult] = []
    errors: List[OCRPageError] = []

    for index, image_path in enumerate(image_paths, start=1):
        resolved_path = Path(image_path).expanduser().resolve()
        page_number = _infer_page_number(resolved_path, fallback=index)
        try:
            text = extract_text_from_image(resolved_path, engine=ocr_engine)
        except Exception as exc:
            page_error = OCRPageError(
                page_number=page_number,
                image_path=resolved_path,
                error_message=str(exc),
            )
            errors.append(page_error)
            if on_error is not None:
                on_error(page_number, resolved_path, exc)
        else:
            results.append(
                OCRPageResult(
                    page_number=page_number,
                    image_path=resolved_path,
                    text=text,
                )
            )
        finally:
            if on_progress is not None:
                on_progress(index, total)

    return OCRBatchResult(pages=results, errors=errors)


def write_text_results(results: Sequence[OCRPageResult], output_path: str | Path) -> Path:
    path = Path(output_path).expanduser().resolve()
    path.parent.mkdir(parents=True, exist_ok=True)

    chunks: List[str] = []
    for result in results:
        chunks.append(f"=== Page {result.page_number} ===\n{result.text}".rstrip())

    path.write_text("\n\n".join(chunks) + ("\n" if chunks else ""), encoding="utf-8")
    return path


def _flatten_ocr_result(raw_result) -> str:
    lines: List[str] = []
    for block in raw_result or []:
        if not block:
            continue
        for line in block:
            if not line or len(line) < 2:
                continue
            candidate = line[1]
            if isinstance(candidate, (list, tuple)) and candidate:
                text = candidate[0]
            else:
                text = candidate
            if isinstance(text, str) and text.strip():
                lines.append(text.strip())
    return "\n".join(lines)


def _extract_lines_with_scores(raw_result) -> list[tuple[str, float]]:
    """Extract (text, confidence) per OCR line from PaddleOCR raw output."""
    lines: list[tuple[str, float]] = []
    for block in raw_result or []:
        if not block:
            continue
        for line in block:
            if not line or len(line) < 2:
                continue
            candidate = line[1]
            if isinstance(candidate, (list, tuple)) and len(candidate) >= 2:
                text, score = candidate[0], candidate[1]
            elif isinstance(candidate, (list, tuple)) and candidate:
                text, score = candidate[0], 1.0
            else:
                text, score = candidate, 1.0
            if not isinstance(text, str) or not text.strip():
                continue
            normalized = _normalize_ocr_text(text.strip())
            if normalized and not _is_noise_line(normalized):
                conf = float(score) if isinstance(score, (int, float)) else 1.0
                lines.append((normalized, max(0.0, min(1.0, conf))))
    return lines


def extract_blocks_from_image(
    image_path: str | Path,
    *,
    engine: Optional[OCREngine] = None,
) -> list[tuple[str, float]]:
    """
    Returns (text, confidence) per OCR line from a single image.
    Applies the same normalization and noise filtering as extract_text_from_image.
    """
    path = Path(image_path).expanduser().resolve()
    if not path.exists():
        raise FileNotFoundError(f"Image file not found: {path}")

    ocr_engine = engine or PaddleOCREngine()
    segment_paths: list[Path] = []
    result: list[tuple[str, float]] = []
    try:
        segment_paths = split_image_for_vertical_ocr(path)
        for segment_path in segment_paths:
            raw = ocr_engine.ocr(str(segment_path), cls=True)
            result.extend(_extract_lines_with_scores(raw))
    except ImagePreprocessingError as exc:
        raise OCRProcessingError(str(exc)) from exc
    except Exception as exc:
        raise OCRProcessingError(f"OCR failed for image: {path}") from exc
    finally:
        for seg in segment_paths:
            seg.unlink(missing_ok=True)
    return result


def _infer_page_number(image_path: Path, *, fallback: int) -> int:
    stem = image_path.stem
    if stem.startswith("page_"):
        suffix = stem.removeprefix("page_")
        if suffix.isdigit():
            return int(suffix)
    return fallback


def _normalize_ocr_text(text: str) -> str:
    normalized = unicodedata.normalize("NFKC", text)
    replacements = {
        "…": "...",
        "—": "-",
        "―": "-",
        "‐": "-",
        "O九": "〇九",
        "O八": "〇八",
        "O七": "〇七",
        "O六": "〇六",
        "O五": "〇五",
        "O四": "〇四",
        "O三": "〇三",
        "O二": "〇二",
        "O一": "〇一",
        "O年": "〇年",
        "0年": "〇年",
        "王子": "甲子",
        "乙王": "乙丑",
        "王": "壬",
        "已": "己",
    }
    for src, dst in replacements.items():
        normalized = normalized.replace(src, dst)

    lines = [_normalize_ocr_line(line.strip()) for line in normalized.splitlines()]
    return "\n".join(line for line in lines if line and not _is_noise_line(line))


def _normalize_ocr_line(line: str) -> str:
    if not line:
        return line
    line = _replace_known_era_tokens(line)
    line = _replace_known_sexagenary_tokens(line)
    return line


def _replace_known_era_tokens(line: str) -> str:
    fuzzy_variants = {
        # 江戸時代・日本年号
        "寛丈": "寛文",
        "元ろ": "元禄",
        "元謙": "元禄",
        "宝氷": "宝永",
        "寛水": "寛永",
        "覚水": "寛永",
        "梵水": "寛永",
        "萬層": "萬暦",
        "萬治": "万治",
        "承麿": "承応",
        "亭保": "享保",
        "魂正": "享保",
        "延亭": "延享",
        "延讃": "延享",
        "贅暦": "宝暦",
        "贄暦": "宝暦",
        "楽壬": "宝暦",
        "天磬": "天和",
        "天享": "天和",
        "駿長": "慶長",
        "文謙": "文政",
        "正保": "正保",
        "顺治": "順治",
        "宗禎": "崇禎",
        # 中国年号
        "康煕": "康熙",
        "乹隆": "乾隆",
        "雍正": "雍正",
    }
    for src, dst in fuzzy_variants.items():
        line = line.replace(src, dst)
    return line


def _replace_known_sexagenary_tokens(line: str) -> str:
    replacements = {
        "甲王": "甲子",
        "乙王": "乙丑",
        "丙笑": "丙寅",
        "丁王": "丁卯",
        "戊笑": "戊寅",
        "庚宙": "庚申",
        "笑末": "癸未",
        "笑亥": "癸亥",
        "笑酉": "癸酉",
        "笑川": "癸丑",
        "笑未": "癸未",
        "茂酉": "戊酉",
        "内辰": "丙辰",
    }
    for src, dst in replacements.items():
        line = line.replace(src, dst)
    return line


def _is_noise_line(line: str) -> bool:
    if len(line) <= 3:
        # 短い行で日本語・漢字・数字がなければノイズ
        has_cjk = any("一" <= ch <= "鿿" or "぀" <= ch <= "ヿ" for ch in line)
        has_digit = any(ch.isdigit() or ch in "〇一二三四五六七八九十百千" for ch in line)
        if not has_cjk and not has_digit:
            return True
    # ASCII記号のみで構成された行を除去
    noise_ratio = sum(1 for ch in line if ch in "!|`'\",.:-_=+/\\()[]{}PpIlı") / max(len(line), 1)
    return noise_ratio > 0.6
