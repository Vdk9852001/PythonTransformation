from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import pandas as pd

from .errors import ErrorCollector


INVALID_MAPPING_VALUES = {"", "NO", "N/A", "NONE", "TBD", "NO DIRECT MAPPING FROM 4.7"}


@dataclass(frozen=True)
class FieldMapping:
    worksheet: str
    target_field: str
    source_table: str | None
    source_field: str | None


def _clean(value: object) -> str:
    return "" if pd.isna(value) else str(value).strip()


def load_field_mappings(path: Path, errors: ErrorCollector) -> list[FieldMapping]:
    """Read the canonical mapping workbook or the legacy two-row mapping CSV folder."""
    mappings: list[FieldMapping] = []
    if path.is_dir():
        for csv_path in sorted(path.glob("*_mapped_fields.csv")):
            raw = pd.read_csv(csv_path, header=None, dtype=str).fillna("")
            if len(raw.index) < 2:
                errors.add("invalid_mapping", "Expected two rows", csv_path.stem)
                continue
            worksheet = csv_path.name.removesuffix("_mapped_fields.csv")
            for target, source in zip(raw.iloc[0], raw.iloc[1]):
                source_parts = _clean(source).split("-", 1)
                target_name = _clean(target).split("-", 1)[-1]
                mappings.append(
                    FieldMapping(
                        worksheet,
                        target_name,
                        source_parts[0].upper() if len(source_parts) == 2 else None,
                        source_parts[1] if len(source_parts) == 2 else None,
                    )
                )
        return mappings

    frame = pd.read_excel(path, dtype=str).fillna("")
    frame.columns = [str(column).strip() for column in frame.columns]
    aliases = {
        "S4_Table": "worksheet",
        "S4_Worksheet": "worksheet",
        "Worksheet": "worksheet",
        "S4_Field": "target",
        "Target_Field": "target",
        "S47_Table": "table",
        "SAP47_Table": "table",
        "S47_Field": "field",
        "SAP47_Field": "field",
    }
    resolved = {canonical: next((c for c, a in aliases.items() if a == canonical and c in frame), None)
                for canonical in {"worksheet", "target", "table", "field"}}
    missing = [name for name, column in resolved.items() if column is None]
    if missing:
        raise ValueError(f"Mapping workbook is missing columns for: {', '.join(missing)}")

    for _, row in frame.iterrows():
        worksheet = _clean(row[resolved["worksheet"]])
        target = _clean(row[resolved["target"]])
        table = _clean(row[resolved["table"]])
        field = _clean(row[resolved["field"]])
        if not worksheet or not target:
            errors.add("invalid_mapping", "Worksheet or target field is blank", worksheet, target)
            continue
        valid_source = table.upper() not in INVALID_MAPPING_VALUES and field.upper() not in INVALID_MAPPING_VALUES
        mappings.append(
            FieldMapping(
                worksheet,
                target,
                table.upper() if valid_source else None,
                field if valid_source else None,
            )
        )
    return mappings


def load_value_mappings(path: Path | None) -> dict[str, dict[str, str]]:
    if path is None:
        return {}
    workbook = pd.ExcelFile(path)
    result: dict[str, dict[str, str]] = {}
    for sheet in workbook.sheet_names:
        frame = workbook.parse(sheet, dtype=str).fillna("")
        frame.columns = [str(column).strip() for column in frame.columns]
        if {"SAP47_Value", "S4_Value"}.issubset(frame.columns):
            result[sheet.strip().upper()] = dict(
                zip(
                    frame["SAP47_Value"].astype(str).str.strip(),
                    frame["S4_Value"].astype(str).str.strip(),
                )
            )
    return result
