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


class EasyOCREngine:
    """OCR engine backed by EasyOCR. Supports Japanese + English on CPU."""

    def __init__(self, langs: list[str] | None = None, gpu: bool = False) -> None:
        try:
            import easyocr
        except ImportError as exc:
            raise OCRProcessingError(
                "easyocr is not installed. Run: pip install easyocr"
            ) from exc

        self._reader = easyocr.Reader(langs or ["ja", "en"], gpu=gpu)

    def ocr(self, img: str, cls: bool = True):
        """Return EasyOCR results in a format compatible with _flatten_ocr_result."""
        results = self._reader.readtext(img)
        # Wrap in the same nested structure expected by _flatten_ocr_result:
        # [[line, ...]] where line = [bbox, (text, conf)]
        return [[[bbox, (text, float(conf))] for bbox, text, conf in results]]


def extract_text_from_image(
    image_path: str | Path,
    *,
    engine: Optional[OCREngine] = None,
) -> str:
    path = Path(image_path).expanduser().resolve()
    if not path.exists():
        raise FileNotFoundError(f"Image file not found: {path}")

    ocr_engine = engine or EasyOCREngine()
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

    ocr_engine = engine or EasyOCREngine()
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
    return "\n".join(line for line in lines if line)


def _normalize_ocr_line(line: str) -> str:
    if not line:
        return line
    line = _replace_known_era_tokens(line)
    line = _replace_known_sexagenary_tokens(line)
    return line


def _replace_known_era_tokens(line: str) -> str:
    fuzzy_variants = {
        "寛丈": "寛文",
        "元ろ": "元禄",
        "宝氷": "宝永",
        "寛水": "寛永",
        "萬層": "萬暦",
        "顺治": "順治",
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
    }
    for src, dst in replacements.items():
        line = line.replace(src, dst)
    return line
