from __future__ import annotations

import copy
import re
import xml.etree.ElementTree as ET
from pathlib import Path

import pandas as pd

from .errors import ErrorCollector

SS = "urn:schemas-microsoft-com:office:spreadsheet"
NS = {"ss": SS}
STYLE = f"{{{SS}}}StyleID"
NAME = f"{{{SS}}}Name"
TYPE = f"{{{SS}}}Type"
EXPANDED_ROWS = f"{{{SS}}}ExpandedRowCount"
INDEX = f"{{{SS}}}Index"

ET.register_namespace("", SS)
ET.register_namespace("ss", SS)
ET.register_namespace("o", "urn:schemas-microsoft-com:office:office")
ET.register_namespace("x", "urn:schemas-microsoft-com:office:excel")
ET.register_namespace("html", "http://www.w3.org/TR/REC-html40")


def _cells(row: ET.Element) -> list[tuple[int, ET.Element]]:
    result: list[tuple[int, ET.Element]] = []
    position = 1
    for cell in row.findall("ss:Cell", NS):
        position = int(cell.get(INDEX, position))
        result.append((position, cell))
        position += 1
    return result


def _value(cell: ET.Element) -> str:
    data = cell.find("ss:Data", NS)
    return "" if data is None or data.text is None else data.text.strip()


def _normalized(value: str) -> str:
    return re.sub(r"[^A-Z0-9_]", "", value.upper().split("-")[-1])


class SpreadsheetMLWriter:
    """Populate an SAP Migration Cockpit template without rebuilding its workbook."""

    def __init__(self, template: Path, errors: ErrorCollector):
        self.template = template
        self.errors = errors
        # ElementTree discards top-level processing instructions. Excel templates
        # commonly contain the mso-application instruction, so retain it verbatim.
        template_text = template.read_text(encoding="utf-8-sig")
        root_match = re.search(r"<(?:\w+:)?Workbook\b", template_text)
        root_offset = root_match.start() if root_match else len(template_text)
        self.processing_instructions = re.findall(
            r"<\?.*?\?>", template_text[:root_offset], flags=re.DOTALL
        )
        self.processing_instructions = [
            item for item in self.processing_instructions
            if not item.lower().startswith("<?xml")
        ]
        self.tree = ET.parse(template)
        self.root = self.tree.getroot()

    def _worksheet(self, name: str) -> ET.Element | None:
        exact = None
        normalized = _normalized(name)
        for worksheet in self.root.findall("ss:Worksheet", NS):
            current = worksheet.get(NAME, "")
            if current == name:
                exact = worksheet
                break
            if _normalized(current) == normalized:
                exact = worksheet
        return exact

    @staticmethod
    def _is_intro(row: ET.Element) -> bool:
        return row.get(STYLE, "").upper() in {"INTRO", "INTRO_UT"} or any(
            cell.get(STYLE, "").upper() in {"INTRO", "INTRO_UT"} for _, cell in _cells(row)
        )

    def populate(self, worksheet_name: str, frame: pd.DataFrame) -> None:
        if worksheet_name.strip().lower() in {"introduction", "field list"}:
            return
        worksheet = self._worksheet(worksheet_name)
        if worksheet is None:
            self.errors.add("template", "Worksheet not found in template", worksheet_name)
            return
        table = worksheet.find("ss:Table", NS)
        if table is None:
            self.errors.add("template", "Worksheet has no Table", worksheet_name)
            return
        rows = table.findall("ss:Row", NS)
        targets = {_normalized(column): column for column in frame.columns}
        header_index, positions = self._locate_header(rows, targets)
        if header_index is None:
            self.errors.add("template", "Could not locate a target-field header row", worksheet_name)
            return

        prototype_index = next(
            (index for index in range(header_index + 1, len(rows)) if not self._is_intro(rows[index])),
            None,
        )
        if prototype_index is None:
            self.errors.add("template", "No data-row prototype found after header", worksheet_name)
            return
        prototype = rows[prototype_index]
        insert_at = list(table).index(prototype)
        table.remove(prototype)
        for record_number, (_, record) in enumerate(frame.iterrows()):
            row = copy.deepcopy(prototype)
            self._populate_row(row, record, positions, worksheet_name, record_number + 1)
            table.insert(insert_at + record_number, row)
        table.set(EXPANDED_ROWS, str(len(table.findall("ss:Row", NS))))

    @staticmethod
    def _locate_header(
        rows: list[ET.Element], targets: dict[str, str]
    ) -> tuple[int | None, dict[str, int]]:
        best_index, best_positions, best_score = None, {}, 0
        for index, row in enumerate(rows):
            if SpreadsheetMLWriter._is_intro(row):
                continue
            positions: dict[str, int] = {}
            for position, cell in _cells(row):
                normalized = _normalized(_value(cell))
                if normalized in targets:
                    positions[targets[normalized]] = position
            if len(positions) > best_score:
                best_index, best_positions, best_score = index, positions, len(positions)
        return best_index, best_positions

    def _populate_row(
        self,
        row: ET.Element,
        record: pd.Series,
        positions: dict[str, int],
        worksheet: str,
        record_number: int,
    ) -> None:
        cells = dict(_cells(row))
        for field, position in positions.items():
            cell = cells.get(position)
            if cell is None:
                cell = ET.Element(f"{{{SS}}}Cell")
                existing_positions = [current for current, _ in _cells(row)]
                cell.set(INDEX, str(position))
                insert_index = next(
                    (i for i, current in enumerate(existing_positions) if current > position),
                    len(existing_positions),
                )
                row.insert(insert_index, cell)
            data = cell.find("ss:Data", NS)
            if data is None:
                data = ET.SubElement(cell, f"{{{SS}}}Data")
            value = record.get(field, "")
            text = "" if pd.isna(value) else str(value)
            data.set(TYPE, "Number" if re.fullmatch(r"-?\d+(?:\.\d+)?", text) and not text.startswith("0") else "String")
            data.text = text
        missing = set(record.index) - set(positions)
        for field in sorted(missing):
            self.errors.add(
                "template_column",
                "Mapped target field was not found in worksheet headers",
                worksheet,
                field,
                record_number,
            )

    def save(self, output: Path) -> None:
        output.parent.mkdir(parents=True, exist_ok=True)
        ET.indent(self.tree, space=" ")
        body = ET.tostring(self.root, encoding="unicode")
        prefix = '<?xml version="1.0" encoding="utf-8"?>\n'
        if self.processing_instructions:
            prefix += "\n".join(self.processing_instructions) + "\n"
        output.write_text(prefix + body, encoding="utf-8")
