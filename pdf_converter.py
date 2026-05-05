from __future__ import annotations

from pathlib import Path
from typing import Iterable, List, Optional, Sequence, Set

from pdf2image import convert_from_path, pdfinfo_from_path


class PDFConversionError(Exception):
    """Raised when a PDF cannot be inspected or converted."""


class PageSelectionError(ValueError):
    """Raised when the page selection string is invalid."""


def ensure_pdf_exists(pdf_path: str | Path) -> Path:
    path = Path(pdf_path).expanduser().resolve()
    if not path.exists():
        raise FileNotFoundError(f"PDF file not found: {path}")
    if path.suffix.lower() != ".pdf":
        raise ValueError(f"Input file is not a PDF: {path}")
    return path


def get_pdf_page_count(pdf_path: str | Path) -> int:
    path = ensure_pdf_exists(pdf_path)
    try:
        info = pdfinfo_from_path(str(path))
    except Exception as exc:  # pragma: no cover - depends on external tool errors
        raise PDFConversionError(f"Failed to inspect PDF metadata: {path}") from exc

    pages = info.get("Pages")
    if not isinstance(pages, int) or pages <= 0:
        raise PDFConversionError(f"Invalid page count reported for PDF: {path}")
    return pages


def parse_page_selection(pages: Optional[str], total_pages: int) -> List[int]:
    if total_pages <= 0:
        raise ValueError("total_pages must be positive")

    if pages is None or not pages.strip():
        return list(range(1, total_pages + 1))

    selected: Set[int] = set()
    parts = [part.strip() for part in pages.split(",") if part.strip()]
    if not parts:
        raise PageSelectionError("Page selection is empty.")

    for part in parts:
        if "-" in part:
            start_text, end_text = part.split("-", 1)
            if not start_text or not end_text:
                raise PageSelectionError(f"Invalid page range: {part}")
            try:
                start = int(start_text)
                end = int(end_text)
            except ValueError as exc:
                raise PageSelectionError(f"Invalid page range: {part}") from exc
            if start <= 0 or end <= 0 or start > end:
                raise PageSelectionError(f"Invalid page range: {part}")
            for page in range(start, end + 1):
                if page > total_pages:
                    raise PageSelectionError(
                        f"Requested page {page} exceeds total pages ({total_pages})."
                    )
                selected.add(page)
        else:
            try:
                page = int(part)
            except ValueError as exc:
                raise PageSelectionError(f"Invalid page number: {part}") from exc
            if page <= 0 or page > total_pages:
                raise PageSelectionError(
                    f"Requested page {page} is outside valid range 1-{total_pages}."
                )
            selected.add(page)

    return sorted(selected)


def convert_pdf_to_images(
    pdf_path: str | Path,
    output_dir: str | Path,
    *,
    dpi: int = 300,
    pages: Optional[str] = None,
    image_format: str = "png",
) -> List[Path]:
    if dpi <= 0:
        raise ValueError("dpi must be positive")

    source = ensure_pdf_exists(pdf_path)
    target_dir = Path(output_dir).expanduser().resolve()
    target_dir.mkdir(parents=True, exist_ok=True)

    total_pages = get_pdf_page_count(source)
    selected_pages = parse_page_selection(pages, total_pages)

    generated: List[Path] = []
    for page_number in selected_pages:
        output_stem = target_dir / f"page_{page_number:03d}"
        try:
            images = convert_from_path(
                str(source),
                dpi=dpi,
                first_page=page_number,
                last_page=page_number,
                fmt=image_format,
                single_file=True,
            )
        except Exception as exc:  # pragma: no cover - depends on poppler runtime
            raise PDFConversionError(
                f"Failed to convert page {page_number} from PDF: {source}"
            ) from exc

        if len(images) != 1:
            raise PDFConversionError(
                f"Expected one image for page {page_number}, got {len(images)}"
            )

        image_path = output_stem.with_suffix(f".{image_format}")
        images[0].save(image_path)
        generated.append(image_path)

    return generated
