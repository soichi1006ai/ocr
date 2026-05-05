from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Iterable, List, Optional, Protocol, Sequence


class OCREngine(Protocol):
    def ocr(self, img: str, cls: bool = True):
        ...


ProgressCallback = Callable[[int, int], None]


@dataclass(frozen=True)
class OCRPageResult:
    page_number: int
    image_path: Path
    text: str


class OCRProcessingError(Exception):
    """Raised when OCR processing cannot continue."""


class PaddleOCREngine:
    def __init__(self, lang: str = "japan", use_angle_cls: bool = True) -> None:
        try:
            from paddleocr import PaddleOCR
        except ImportError as exc:  # pragma: no cover - depends on optional dependency
            raise OCRProcessingError(
                "paddleocr is not installed. Install dependencies from requirements.txt first."
            ) from exc

        self._engine = PaddleOCR(lang=lang, use_angle_cls=use_angle_cls)

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
    try:
        raw_result = ocr_engine.ocr(str(path), cls=True)
    except Exception as exc:  # pragma: no cover - third-party runtime behavior
        raise OCRProcessingError(f"OCR failed for image: {path}") from exc

    return _flatten_ocr_result(raw_result)



def extract_text_from_images(
    image_paths: Sequence[str | Path],
    *,
    engine: Optional[OCREngine] = None,
    on_progress: Optional[ProgressCallback] = None,
) -> List[OCRPageResult]:
    if not image_paths:
        return []

    ocr_engine = engine or PaddleOCREngine()
    total = len(image_paths)
    results: List[OCRPageResult] = []

    for index, image_path in enumerate(image_paths, start=1):
        text = extract_text_from_image(image_path, engine=ocr_engine)
        results.append(
            OCRPageResult(
                page_number=index,
                image_path=Path(image_path).expanduser().resolve(),
                text=text,
            )
        )
        if on_progress is not None:
            on_progress(index, total)

    return results



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
