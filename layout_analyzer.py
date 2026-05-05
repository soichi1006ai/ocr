from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, List, Optional, Protocol, Sequence


class LayoutAnalyzerEngine(Protocol):
    def __call__(self, img: str):
        ...


@dataclass(frozen=True)
class LayoutRegion:
    page_number: int
    region_type: str
    bbox: list[int] | list[float] | None
    raw: dict[str, Any]


class LayoutAnalysisError(Exception):
    """Raised when page layout analysis fails."""


class PPStructureEngine:
    def __init__(self, lang: str = "japan", show_log: bool = False) -> None:
        try:
            from paddleocr import PPStructure
        except ImportError as exc:  # pragma: no cover
            raise LayoutAnalysisError(
                "paddleocr is not installed. Install dependencies from requirements.txt first."
            ) from exc

        self._engine = PPStructure(lang=lang, show_log=show_log)

    def __call__(self, img: str):
        return self._engine(img)



def analyze_page_layout(
    image_path: str | Path,
    page_number: int,
    *,
    engine: Optional[LayoutAnalyzerEngine] = None,
) -> list[LayoutRegion]:
    path = Path(image_path).expanduser().resolve()
    if not path.exists():
        raise FileNotFoundError(f"Image file not found: {path}")

    analyzer = engine or PPStructureEngine()
    try:
        raw_regions = analyzer(str(path))
    except Exception as exc:  # pragma: no cover
        raise LayoutAnalysisError(f"Layout analysis failed for image: {path}") from exc

    regions: list[LayoutRegion] = []
    for raw in raw_regions or []:
        if not isinstance(raw, dict):
            continue
        regions.append(
            LayoutRegion(
                page_number=page_number,
                region_type=str(raw.get("type", "unknown")),
                bbox=raw.get("bbox"),
                raw=raw,
            )
        )
    return regions



def analyze_document_layout(
    image_paths: Sequence[str | Path],
    *,
    engine: Optional[LayoutAnalyzerEngine] = None,
) -> list[LayoutRegion]:
    analyzer = engine or PPStructureEngine()
    results: list[LayoutRegion] = []
    for index, image_path in enumerate(image_paths, start=1):
        results.extend(analyze_page_layout(image_path, index, engine=analyzer))
    return results
