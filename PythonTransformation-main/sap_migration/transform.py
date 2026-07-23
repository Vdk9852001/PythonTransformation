from __future__ import annotations

from collections import defaultdict
from pathlib import Path

import pandas as pd

from .errors import ErrorCollector
from .mapping import FieldMapping


ENTITY_KEYS: dict[str, list[str]] = {
    "MARA": ["MATNR"],
    "MAKT": ["MATNR", "SPRAS"],
    "MARC": ["MATNR", "WERKS"],
    "MBEW": ["MATNR", "BWKEY", "BWTAR"],
    "MLAN": ["MATNR", "ALAND"],
    "MARM": ["MATNR", "MEINH"],
    "MLGN": ["MATNR", "LGNUM"],
    "MLGT": ["MATNR", "LGNUM", "LGTYP"],
}
ANCHOR_PRIORITY = ("MLGT", "MLGN", "MARM", "MLAN", "MBEW", "MARC", "MAKT", "MARA")

WAERS_BY_BWKEY = {
    "USP1": "USD", "USP2": "USD", "USP3": "USD", "USP4": "USD", "UPS5": "USD", "USP6": "USD",
    "CNP1": "CNY", "CNP2": "CNY", "CHP1": "CHF", "CHP2": "CHF", "DEP1": "EUR",
    "SGP1": "SGD", "SGP2": "SGD", "SGP3": "SGD", "MXP1": "MXN", "MXP2": "MXN",
}
ENTITLED_BY_LGNUM = {
    "BRN1": "20000036", "MAT1": "20000036", "PU01": "40000003",
    "PU02": "20000035", "SH02": "20000037",
}


def load_legacy_tables(folder: Path, errors: ErrorCollector, language: str = "E") -> dict[str, pd.DataFrame]:
    tables: dict[str, pd.DataFrame] = {}
    for path in sorted(folder.glob("*.csv")):
        try:
            frame = pd.read_csv(path, dtype=str, keep_default_na=False, on_bad_lines="warn")
            frame.columns = [str(column).strip().upper() for column in frame.columns]
            for column in frame.columns:
                frame[column] = frame[column].astype(str).str.strip()
            if "MATNR" in frame:
                frame["MATNR"] = frame["MATNR"].map(
                    lambda value: value.zfill(18) if value.isdigit() else value
                )
            if path.stem.upper() == "MAKT" and "SPRAS" in frame:
                frame = frame[frame["SPRAS"].str.upper() == language.upper()]
            tables[path.stem.upper()] = frame.reset_index(drop=True)
        except Exception as exc:
            errors.add("source_load", str(exc), value=path.name)
    return tables


def _anchor_table(mappings: list[FieldMapping], tables: dict[str, pd.DataFrame]) -> str | None:
    referenced = {mapping.source_table for mapping in mappings if mapping.source_table}
    return next((table for table in ANCHOR_PRIORITY if table in referenced and table in tables), None)


def build_entity_frame(
    worksheet: str,
    mappings: list[FieldMapping],
    tables: dict[str, pd.DataFrame],
    errors: ErrorCollector,
) -> pd.DataFrame:
    """Build one correctly-grained source frame per SAP worksheet."""
    anchor = _anchor_table(mappings, tables)
    if anchor is None:
        errors.add("missing_source", "No available source table can anchor the worksheet", worksheet)
        return pd.DataFrame()
    result = tables[anchor].copy()
    required = {mapping.source_table for mapping in mappings if mapping.source_table}

    for table_name in sorted(required - {anchor}):
        source = tables.get(table_name)
        if source is None:
            errors.add("missing_table", f"Source table {table_name} was not loaded", worksheet)
            continue
        common_keys = [
            key for key in ENTITY_KEYS.get(table_name, ["MATNR"])
            if key in result.columns and key in source.columns
        ]
        if not common_keys and "MATNR" in result.columns and "MATNR" in source.columns:
            common_keys = ["MATNR"]
        if not common_keys:
            errors.add("join", f"No common join key for {anchor} -> {table_name}", worksheet)
            continue
        right = source.copy()
        duplicates = right.duplicated(common_keys, keep=False)
        if duplicates.any():
            errors.add(
                "join_cardinality",
                f"{table_name} has duplicate rows for {common_keys}; first row retained",
                worksheet,
                value=int(duplicates.sum()),
            )
            right = right.drop_duplicates(common_keys, keep="first")
        rename = {column: f"{table_name}__{column}" for column in right.columns if column not in common_keys}
        result = result.merge(right.rename(columns=rename), on=common_keys, how="left", validate="many_to_one")
    return result


def _source_column(frame: pd.DataFrame, anchor: str, table: str, field: str) -> str | None:
    field = field.upper()
    if table == anchor and field in frame.columns:
        return field
    qualified = f"{table}__{field}"
    if qualified in frame.columns:
        return qualified
    if field in frame.columns:
        return field
    return None


def apply_mappings(
    worksheet: str,
    mappings: list[FieldMapping],
    source: pd.DataFrame,
    tables: dict[str, pd.DataFrame],
    value_mappings: dict[str, dict[str, str]],
    errors: ErrorCollector,
) -> pd.DataFrame:
    anchor = _anchor_table(mappings, tables)
    if anchor is None or source.empty:
        return pd.DataFrame(columns=[mapping.target_field for mapping in mappings])
    output = pd.DataFrame(index=source.index)
    for mapping in mappings:
        if not mapping.source_table or not mapping.source_field:
            output[mapping.target_field] = ""
            errors.add("missing_mapping", "No direct source mapping", worksheet, mapping.target_field)
            continue
        source_column = _source_column(source, anchor, mapping.source_table, mapping.source_field)
        if source_column is None:
            output[mapping.target_field] = ""
            errors.add(
                "missing_column",
                f"{mapping.source_table}-{mapping.source_field} is unavailable",
                worksheet,
                mapping.target_field,
            )
            continue
        original = source[source_column].fillna("").astype(str).str.strip()
        map_key = mapping.target_field.split("-")[-1].upper()
        map_key = "WERK" if "WERK" in map_key else map_key
        value_map = value_mappings.get(map_key)
        if value_map:
            mapped = original.map(value_map)
            for value in sorted(original[(mapped.isna()) & original.ne("")].unique()):
                errors.add("unmapped_value", "Original value retained", worksheet, mapping.target_field, value)
            output[mapping.target_field] = mapped.fillna(original)
        else:
            output[mapping.target_field] = original
    return apply_business_rules(output, worksheet, errors)


def _find_column(frame: pd.DataFrame, suffix: str) -> str | None:
    return next((column for column in frame if column.upper().split("-")[-1] == suffix), None)


def apply_business_rules(frame: pd.DataFrame, worksheet: str, errors: ErrorCollector) -> pd.DataFrame:
    waers, bwkey = _find_column(frame, "WAERS"), _find_column(frame, "BWKEY")
    if waers and bwkey:
        normalized = frame[bwkey].astype(str).str.strip().str.upper()
        derived = normalized.map(WAERS_BY_BWKEY)
        for value in sorted(normalized[derived.isna() & normalized.ne("")].unique()):
            errors.add("business_rule", "No WAERS mapping for BWKEY", worksheet, waers, value)
        frame[waers] = derived.fillna(frame[waers])
    mlast = _find_column(frame, "MLAST")
    if mlast:
        frame[mlast] = "3"
    curtp = _find_column(frame, "CURTP")
    if curtp:
        frame[curtp] = "10"
    entitled, lgnum = _find_column(frame, "ENTITLED"), _find_column(frame, "LGNUM")
    if entitled and lgnum:
        normalized = frame[lgnum].astype(str).str.strip().str.upper()
        derived = normalized.map(ENTITLED_BY_LGNUM)
        for value in sorted(normalized[derived.isna() & normalized.ne("")].unique()):
            errors.add("business_rule", "No ENTITLED mapping for LGNUM", worksheet, entitled, value)
        frame[entitled] = derived.fillna(frame[entitled])
    return frame


def group_mappings(mappings: list[FieldMapping]) -> dict[str, list[FieldMapping]]:
    result: dict[str, list[FieldMapping]] = defaultdict(list)
    for mapping in mappings:
        result[mapping.worksheet].append(mapping)
    return dict(result)
