from __future__ import annotations

import argparse
import sys
from pathlib import Path

from pdf_converter import PDFConversionError, PageSelectionError, convert_pdf_to_images
from docx_exporter import DocxExportError, write_docx_results
from layout_analyzer import LayoutAnalysisError, analyze_document_layout
from table_extractor import TableExtractionError, extract_tables, write_tables_to_workbook
from text_extractor import OCRProcessingError, extract_text_from_images, write_text_results



def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Extract text from scanned PDFs using PaddleOCR."
    )
    parser.add_argument("input", help="Input PDF path")
    parser.add_argument(
        "--output",
        default="./output",
        help="Output directory for generated files (default: ./output)",
    )
    parser.add_argument(
        "--pages",
        default=None,
        help="Page selection like 1,3-5 (default: all pages)",
    )
    parser.add_argument(
        "--dpi",
        type=int,
        default=300,
        help="Render DPI for PDF to image conversion (default: 300)",
    )
    return parser



def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    output_dir = Path(args.output).expanduser().resolve()
    pages_dir = output_dir / "pages"

    try:
        image_paths = convert_pdf_to_images(
            args.input,
            pages_dir,
            dpi=args.dpi,
            pages=args.pages,
        )
        results = extract_text_from_images(image_paths, on_progress=_print_progress)
        result_path = write_text_results(results, output_dir / "result.txt")
        layout_regions = analyze_document_layout(image_paths)
        tables = extract_tables(layout_regions)
        workbook_path = write_tables_to_workbook(tables, output_dir / "tables.xlsx")
        docx_path = write_docx_results(results, tables, output_dir / "result.docx")
    except (FileNotFoundError, ValueError, PageSelectionError) as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1
    except (PDFConversionError, OCRProcessingError, LayoutAnalysisError, TableExtractionError, DocxExportError) as exc:
        print(f"Processing failed: {exc}", file=sys.stderr)
        return 2

    print(f"Done: text output written to {result_path}")
    if workbook_path is not None:
        print(f"Done: table output written to {workbook_path}")
    else:
        print("Warning: no tables detected; tables.xlsx was not created")
    print(f"Done: Word output written to {docx_path}")
    return 0



def _print_progress(current_page: int, total_pages: int) -> None:
    print(f"[{current_page}/{total_pages}] ページ {current_page} を処理中...")


if __name__ == "__main__":
    raise SystemExit(main())
