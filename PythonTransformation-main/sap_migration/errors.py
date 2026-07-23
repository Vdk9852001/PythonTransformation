from __future__ import annotations

import csv
import logging
from dataclasses import asdict, dataclass
from pathlib import Path


@dataclass(frozen=True)
class MigrationError:
    category: str
    message: str
    worksheet: str = ""
    field: str = ""
    value: str = ""


class ErrorCollector:
    """Collects recoverable migration problems while also writing them to the log."""

    def __init__(self, logger: logging.Logger):
        self.logger = logger
        self.items: list[MigrationError] = []

    def add(
        self,
        category: str,
        message: str,
        worksheet: str = "",
        field: str = "",
        value: object = "",
    ) -> None:
        error = MigrationError(category, message, worksheet, field, str(value))
        self.items.append(error)
        self.logger.warning(
            "%s: %s [worksheet=%s, field=%s, value=%s]",
            category,
            message,
            worksheet,
            field,
            value,
        )

    def write_csv(self, path: Path) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("w", newline="", encoding="utf-8-sig") as handle:
            writer = csv.DictWriter(handle, fieldnames=list(MigrationError.__annotations__))
            writer.writeheader()
            writer.writerows(asdict(item) for item in self.items)

    def show_dialog(self) -> None:
        """Show a summary when a desktop is available; silently fall back to the report."""
        if not self.items:
            return
        try:
            from tkinter import messagebox

            messagebox.showwarning(
                "Migration completed with observations",
                f"{len(self.items)} issue(s) were collected. See the error report for details.",
            )
        except Exception:
            self.logger.info("A desktop error dialog was unavailable.")
