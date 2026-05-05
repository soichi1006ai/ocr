from __future__ import annotations

from dataclasses import dataclass
from html.parser import HTMLParser
from pathlib import Path
from typing import Any, Iterable, List, Optional, Sequence

from openpyxl import Workbook

from layout_analyzer import LayoutRegion


@dataclass(frozen=True)
class TableData:
    page_number: int
    table_index: int
    rows: list[list[str]]

    @property
    def sheet_name(self) -> str:
        return f"table_{self.page_number}_{self.table_index}"


class TableExtractionError(Exception):
    """Raised when table extraction cannot proceed."""


class _SimpleHTMLTableParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.rows: list[list[str]] = []
        self._current_row: list[str] = []
        self._cell_chunks: list[str] = []
        self._in_cell = False

    def handle_starttag(self, tag: str, attrs) -> None:
        if tag == "tr":
            self._current_row = []
        elif tag in {"td", "th"}:
            self._in_cell = True
            self._cell_chunks = []

    def handle_data(self, data: str) -> None:
        if self._in_cell:
            self._cell_chunks.append(data)

    def handle_endtag(self, tag: str) -> None:
        if tag in {"td", "th"}:
            self._in_cell = False
            text = " ".join(chunk.strip() for chunk in self._cell_chunks if chunk.strip())
            self._current_row.append(text)
            self._cell_chunks = []
        elif tag == "tr":
            if self._current_row:
                self.rows.append(self._current_row)
            self._current_row = []



def extract_tables(regions: Sequence[LayoutRegion]) -> list[TableData]:
    tables: list[TableData] = []
    table_counts: dict[int, int] = {}

    for region in regions:
        if region.region_type != "table":
            continue

        table_counts[region.page_number] = table_counts.get(region.page_number, 0) + 1
        table_index = table_counts[region.page_number]
        rows = _extract_rows_from_region(region.raw)
        tables.append(TableData(page_number=region.page_number, table_index=table_index, rows=rows))

    return tables



def write_tables_to_workbook(tables: Sequence[TableData], output_path: str | Path) -> Optional[Path]:
    if not tables:
        return None

    path = Path(output_path).expanduser().resolve()
    path.parent.mkdir(parents=True, exist_ok=True)

    workbook = Workbook()
    default_sheet = workbook.active
    workbook.remove(default_sheet)

    for table in tables:
        sheet = workbook.create_sheet(title=table.sheet_name[:31])
        for row_index, row in enumerate(table.rows, start=1):
            for col_index, value in enumerate(row, start=1):
                sheet.cell(row=row_index, column=col_index, value=value)

    workbook.save(path)
    return path



def _extract_rows_from_region(raw_region: dict[str, Any]) -> list[list[str]]:
    html = raw_region.get("res", {}).get("html")
    if isinstance(html, str) and html.strip():
        rows = _parse_html_table(html)
        if rows:
            return rows

    text = raw_region.get("res", {}).get("text")
    if isinstance(text, list):
        rows = [[str(cell) for cell in row] for row in text if isinstance(row, list)]
        if rows:
            return rows

    return []



def _parse_html_table(html: str) -> list[list[str]]:
    parser = _SimpleHTMLTableParser()
    parser.feed(html)
    parser.close()
    return parser.rows
