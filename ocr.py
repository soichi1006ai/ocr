from __future__ import annotations

import argparse
import sys
from pathlib import Path

from exporters.docx_exporter import DocxExportError, write_docx_results
from engines.paddle_internal.layout_analyzer import LayoutAnalysisError, analyze_document_layout
from pdf_converter import PDFConversionError, PageSelectionError, convert_pdf_to_images
from exporters.table_extractor import TableExtractionError, extract_tables, write_tables_to_workbook
from text_extractor import OCRProcessingError, extract_text_from_images, write_text_results



def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Extract text and tables from scanned PDFs."
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
    parser.add_argument(
        "--engine",
        choices=["paddleocr", "ndlocr", "claude", "hybrid"],
        default="paddleocr",
        help="OCR engine: paddleocr / ndlocr / claude / hybrid",
    )
    parser.add_argument(
        "--api-key",
        default=None,
        help="Anthropic API key for Claude engine (default: ANTHROPIC_API_KEY env var)",
    )
    parser.add_argument(
        "--document-type",
        choices=["auto", "koyomi", "daichou", "honbun"],
        default="auto",
        help="Document type hint for the OCR engine",
    )
    parser.add_argument(
        "--model",
        default=None,
        help="Claude model ID (e.g. claude-opus-4-7, claude-sonnet-4-6)",
    )
    parser.add_argument(
        "--confidence-threshold",
        type=float,
        default=0.85,
        help="Confidence threshold for hybrid engine (0.0-1.0, default: 0.85)",
    )
    parser.add_argument(
        "--spread",
        action="store_true",
        default=False,
        help="Split each page into left/right halves and deskew independently (for spread scans)",
    )
    parser.add_argument(
        "--formats",
        nargs="+",
        choices=["txt", "xlsx", "docx"],
        default=["txt", "xlsx", "docx"],
        help="Output formats to generate (default: all)",
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

        if args.spread:
            from image_preprocessor import split_spread_pages
            image_paths = split_spread_pages(image_paths, pages_dir)
            print(f"[spread: {len(image_paths)} half-pages]")

        print(f"[engine: {args.engine}]")

        if args.engine == "hybrid":
            from engines.hybrid_engine import HybridEngine
            from engines.base import DocumentType
            doc_type = DocumentType(args.document_type)
            engine = HybridEngine(
                api_key=args.api_key or None,
                confidence_threshold=args.confidence_threshold,
            )
            def _hybrid_progress(current, total, msg):
                print(f"[{current}/{total}] {msg}")
            result = engine.extract(image_paths, doc_type, on_progress=_hybrid_progress)
            if not result.pages:
                raise Exception("Hybrid OCR: 全ページ失敗")
            output_dir.mkdir(parents=True, exist_ok=True)
            fmt = set(args.formats)
            raw_text = result.all_raw_text()
            if "txt" in fmt:
                txt_path = output_dir / "result.txt"
                txt_path.write_text(raw_text, encoding="utf-8")
                print(f"Done: text output written to {txt_path}")
            if "xlsx" in fmt:
                from exporters.table_extractor import write_tables_to_workbook
                tables = []
                for page in result.pages:
                    tables.extend(page.table_blocks)
                if tables:
                    wb_path = write_tables_to_workbook(tables, output_dir / "tables.xlsx")
                    if wb_path:
                        print(f"Done: Excel output written to {wb_path}")
            if "docx" in fmt:
                from exporters.docx_exporter import write_docx_results
                docx_path = write_docx_results(result.pages, [], output_dir / "result.docx")
                if docx_path:
                    print(f"Done: Word output written to {docx_path}")
            if result.errors:
                for e in result.errors:
                    print(f"Warning: page {e.page_number} failed: {e.message}", file=sys.stderr)
            return 0

        elif args.engine == "claude":
            from claude_engine import ClaudeOCRError, extract_tables_claude, run_claude_ocr
            api_key = args.api_key or None
            ocr_batch = run_claude_ocr(
                image_paths,
                api_key=api_key,
                on_progress=_print_progress,
                on_error=_print_page_error,
            )
            if not ocr_batch.pages:
                raise OCRProcessingError("Claude OCR failed for all pages.")
            tables = extract_tables_claude(image_paths, api_key=api_key)
            layout_batch = None
        elif args.engine == "ndlocr":
            from engines.ndlocr_engine import NDLOCRError, extract_tables_ndlocr, run_ndlocr
            ocr_batch = run_ndlocr(
                image_paths,
                on_progress=_print_progress,
                on_error=_print_page_error,
            )
            if not ocr_batch.pages:
                raise OCRProcessingError("ndlocr-lite failed for all pages.")
            tables = extract_tables_ndlocr(image_paths)
            layout_batch = None
        else:
            ocr_batch = extract_text_from_images(
                image_paths,
                on_progress=_print_progress,
                on_error=_print_page_error,
            )
            if not ocr_batch.pages:
                raise OCRProcessingError("OCR failed for all pages.")
            layout_batch = analyze_document_layout(
                image_paths,
                on_error=_print_layout_error,
            )
            image_path_by_page = {
                int(p.stem.removeprefix("page_")): p
                for p in image_paths
                if p.stem.startswith("page_") and p.stem.removeprefix("page_").isdigit()
            }
            tables = extract_tables(layout_batch.regions, image_paths=image_path_by_page)

        fmt = set(args.formats)
        result_path = write_text_results(ocr_batch.pages, output_dir / "result.txt") if "txt" in fmt else None
        workbook_path = write_tables_to_workbook(tables, output_dir / "tables.xlsx") if "xlsx" in fmt else None
        docx_path = write_docx_results(ocr_batch.pages, tables, output_dir / "result.docx") if "docx" in fmt else None
    except (FileNotFoundError, ValueError, PageSelectionError) as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1
    except (PDFConversionError, OCRProcessingError, LayoutAnalysisError, TableExtractionError, DocxExportError, Exception) as exc:
        print(f"Processing failed: {exc}", file=sys.stderr)
        return 2

    if result_path:
        print(f"Done: text output written to {result_path}")
    if workbook_path is not None:
        print(f"Done: table output written to {workbook_path}")
    elif "xlsx" in set(args.formats):
        print("Warning: no tables detected; tables.xlsx was not created")
    if docx_path:
        print(f"Done: Word output written to {docx_path}")

    if args.engine == "paddleocr" and layout_batch is not None:
        frame_candidates = [r for r in layout_batch.regions if r.region_type in {"frame_candidate", "table_frame_candidate"}]
        table_like_candidates = [r for r in frame_candidates if r.region_type == "table_frame_candidate"]
        if frame_candidates:
            print(f"Info: detected {len(frame_candidates)} frame candidate(s), {len(table_like_candidates)} table-like")
        if layout_batch.errors:
            print(
                f"Warning: layout analysis failed on {len(layout_batch.errors)} page(s); "
                "table output may be incomplete"
            )

    if ocr_batch.errors:
        print(f"Warning: OCR failed on {len(ocr_batch.errors)} page(s); see stderr warnings above")
    return 0



def _print_progress(current_page: int, total_pages: int) -> None:
    print(f"[{current_page}/{total_pages}] ページ {current_page} を処理中...")



def _print_page_error(current_page: int, image_path: Path, exc: Exception) -> None:
    print(
        f"Warning: page {current_page} OCR failed and was skipped ({image_path.name}): {exc}",
        file=sys.stderr,
    )



def _print_layout_error(current_page: int, image_path: Path, exc: Exception) -> None:
    print(
        f"Warning: page {current_page} layout analysis failed and was skipped ({image_path.name}): {exc}",
        file=sys.stderr,
    )


if __name__ == "__main__":
    raise SystemExit(main())
