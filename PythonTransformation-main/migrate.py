from __future__ import annotations

import argparse
from pathlib import Path

from sap_migration import MigrationPipeline, PipelineConfig


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Transform SAP 4.7 extracts into an S/4HANA Migration Cockpit SpreadsheetML workbook."
    )
    parser.add_argument("--source-folder", required=True, type=Path)
    parser.add_argument("--field-mapping", required=True, type=Path)
    parser.add_argument("--value-mapping", type=Path)
    parser.add_argument("--sap-template", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--error-report", type=Path)
    parser.add_argument("--log-file", type=Path)
    parser.add_argument("--language", default="E")
    parser.add_argument("--show-error-dialog", action="store_true")
    args = parser.parse_args()

    config = PipelineConfig(
        source_folder=args.source_folder,
        field_mapping=args.field_mapping,
        value_mapping=args.value_mapping,
        sap_template=args.sap_template,
        output_xml=args.output,
        error_report=args.error_report,
        log_file=args.log_file,
        language=args.language,
        show_error_dialog=args.show_error_dialog,
    )
    MigrationPipeline(config).run()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
