from __future__ import annotations

import logging
from dataclasses import dataclass
from pathlib import Path

from .errors import ErrorCollector
from .mapping import load_field_mappings, load_value_mappings
from .spreadsheetml import SpreadsheetMLWriter
from .transform import apply_mappings, build_entity_frame, group_mappings, load_legacy_tables


@dataclass(frozen=True)
class PipelineConfig:
    source_folder: Path
    field_mapping: Path
    sap_template: Path
    output_xml: Path
    value_mapping: Path | None = None
    error_report: Path | None = None
    log_file: Path | None = None
    language: str = "E"
    show_error_dialog: bool = False


class MigrationPipeline:
    def __init__(self, config: PipelineConfig):
        self.config = config
        log_path = config.log_file or config.output_xml.with_suffix(".log")
        log_path.parent.mkdir(parents=True, exist_ok=True)
        self.logger = logging.getLogger(f"sap_migration.{id(self)}")
        self.logger.setLevel(logging.INFO)
        self.logger.addHandler(logging.FileHandler(log_path, encoding="utf-8"))
        self.logger.addHandler(logging.StreamHandler())
        self.errors = ErrorCollector(self.logger)

    def run(self) -> int:
        self.logger.info("Loading SAP 4.7 source extracts")
        tables = load_legacy_tables(self.config.source_folder, self.errors, self.config.language)
        mappings = load_field_mappings(self.config.field_mapping, self.errors)
        value_mappings = load_value_mappings(self.config.value_mapping)
        writer = SpreadsheetMLWriter(self.config.sap_template, self.errors)

        for worksheet, worksheet_mappings in group_mappings(mappings).items():
            self.logger.info("Transforming worksheet: %s", worksheet)
            source = build_entity_frame(worksheet, worksheet_mappings, tables, self.errors)
            final = apply_mappings(
                worksheet, worksheet_mappings, source, tables, value_mappings, self.errors
            )
            writer.populate(worksheet, final)

        writer.save(self.config.output_xml)
        report = self.config.error_report or self.config.output_xml.with_name("migration_errors.csv")
        self.errors.write_csv(report)
        if self.config.show_error_dialog:
            self.errors.show_dialog()
        self.logger.info(
            "Migration complete: %s (%d observation(s))",
            self.config.output_xml,
            len(self.errors.items),
        )
        return len(self.errors.items)
