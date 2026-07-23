from __future__ import annotations

import logging
import queue
import threading
import tkinter as tk
from pathlib import Path
from tkinter import filedialog, messagebox, ttk

from sap_migration import MigrationPipeline, PipelineConfig


class QueueLogHandler(logging.Handler):
    def __init__(self, messages: queue.Queue[tuple[str, object]]):
        super().__init__()
        self.messages = messages

    def emit(self, record: logging.LogRecord) -> None:
        self.messages.put(("log", self.format(record)))


class MigrationApp(tk.Tk):
    def __init__(self) -> None:
        super().__init__()
        self.title("SAP 4.7 to S/4HANA Product Migration")
        self.geometry("920x690")
        self.minsize(760, 600)

        self.messages: queue.Queue[tuple[str, object]] = queue.Queue()
        self.running = False
        self.variables = {
            "source": tk.StringVar(),
            "field_mapping": tk.StringVar(),
            "value_mapping": tk.StringVar(),
            "template": tk.StringVar(),
            "output": tk.StringVar(),
            "error_report": tk.StringVar(),
            "log_file": tk.StringVar(),
            "language": tk.StringVar(value="E"),
        }
        self._build_ui()
        self.after(100, self._drain_messages)

    def _build_ui(self) -> None:
        container = ttk.Frame(self, padding=18)
        container.pack(fill="both", expand=True)
        container.columnconfigure(1, weight=1)
        container.rowconfigure(10, weight=1)

        ttk.Label(
            container,
            text="SAP 4.7 → S/4HANA Product Migration",
            font=("TkDefaultFont", 16, "bold"),
        ).grid(row=0, column=0, columnspan=3, sticky="w", pady=(0, 4))
        ttk.Label(
            container,
            text="Populate an SAP Migration Cockpit SpreadsheetML template from SAP 4.7 extracts.",
        ).grid(row=1, column=0, columnspan=3, sticky="w", pady=(0, 16))

        fields = [
            ("SAP 4.7 CSV folder", "source", "folder", True),
            ("Field mapping", "field_mapping", "excel_or_folder", True),
            ("Value mapping", "value_mapping", "excel", False),
            ("SAP XML template", "template", "xml", True),
            ("Output XML", "output", "save_xml", True),
            ("Error report", "error_report", "save_csv", False),
            ("Log file", "log_file", "save_log", False),
        ]
        for offset, (label, key, browse_type, required) in enumerate(fields, start=2):
            label_text = f"{label} *" if required else label
            ttk.Label(container, text=label_text).grid(
                row=offset, column=0, sticky="w", padx=(0, 12), pady=4
            )
            ttk.Entry(container, textvariable=self.variables[key]).grid(
                row=offset, column=1, sticky="ew", pady=4
            )
            ttk.Button(
                container,
                text="Browse…",
                command=lambda k=key, kind=browse_type: self._browse(k, kind),
            ).grid(row=offset, column=2, padx=(8, 0), pady=4)

        options = ttk.Frame(container)
        options.grid(row=9, column=0, columnspan=3, sticky="ew", pady=(10, 8))
        ttk.Label(options, text="MAKT language").pack(side="left")
        ttk.Entry(options, textvariable=self.variables["language"], width=6).pack(
            side="left", padx=(8, 20)
        )
        ttk.Label(options, text="* Required").pack(side="right")

        log_frame = ttk.LabelFrame(container, text="Processing log", padding=8)
        log_frame.grid(row=10, column=0, columnspan=3, sticky="nsew")
        log_frame.columnconfigure(0, weight=1)
        log_frame.rowconfigure(0, weight=1)
        self.log_text = tk.Text(log_frame, height=12, wrap="word", state="disabled")
        scrollbar = ttk.Scrollbar(log_frame, orient="vertical", command=self.log_text.yview)
        self.log_text.configure(yscrollcommand=scrollbar.set)
        self.log_text.grid(row=0, column=0, sticky="nsew")
        scrollbar.grid(row=0, column=1, sticky="ns")

        footer = ttk.Frame(container)
        footer.grid(row=11, column=0, columnspan=3, sticky="ew", pady=(12, 0))
        footer.columnconfigure(0, weight=1)
        self.progress = ttk.Progressbar(footer, mode="indeterminate")
        self.progress.grid(row=0, column=0, sticky="ew", padx=(0, 12))
        self.run_button = ttk.Button(footer, text="Generate SAP XML", command=self._start)
        self.run_button.grid(row=0, column=1)

    def _browse(self, key: str, kind: str) -> None:
        excel_types = [("Excel workbooks", "*.xlsx *.xls"), ("All files", "*.*")]
        if kind == "folder":
            selected = filedialog.askdirectory(title="Select CSV extract folder")
        elif kind == "excel_or_folder":
            selected = filedialog.askopenfilename(title="Select field mapping", filetypes=excel_types)
            if not selected and messagebox.askyesno(
                "Legacy field mappings", "Select a folder of *_mapped_fields.csv files instead?"
            ):
                selected = filedialog.askdirectory(title="Select field mapping folder")
        elif kind == "excel":
            selected = filedialog.askopenfilename(title="Select value mapping", filetypes=excel_types)
        elif kind == "xml":
            selected = filedialog.askopenfilename(
                title="Select SAP SpreadsheetML template",
                filetypes=[("Excel 2003 XML", "*.xml"), ("All files", "*.*")],
            )
        else:
            filetypes = {
                "save_xml": [("Excel 2003 XML", "*.xml")],
                "save_csv": [("CSV report", "*.csv")],
                "save_log": [("Log file", "*.log"), ("Text file", "*.txt")],
            }[kind]
            extensions = {"save_xml": ".xml", "save_csv": ".csv", "save_log": ".log"}
            selected = filedialog.asksaveasfilename(
                title=f"Choose {key.replace('_', ' ')}",
                defaultextension=extensions[kind],
                filetypes=filetypes,
            )
        if selected:
            self.variables[key].set(selected)
            if key == "template" and not self.variables["output"].get():
                template = Path(selected)
                self.variables["output"].set(str(template.with_name(f"{template.stem}_output.xml")))

    def _validate(self) -> PipelineConfig | None:
        required = {
            "source": "SAP 4.7 CSV folder",
            "field_mapping": "field mapping",
            "template": "SAP XML template",
            "output": "output XML",
        }
        missing = [label for key, label in required.items() if not self.variables[key].get().strip()]
        if missing:
            messagebox.showerror("Missing inputs", "Select: " + ", ".join(missing) + ".")
            return None

        source = Path(self.variables["source"].get()).expanduser()
        field_mapping = Path(self.variables["field_mapping"].get()).expanduser()
        template = Path(self.variables["template"].get()).expanduser()
        value_text = self.variables["value_mapping"].get().strip()
        paths_to_check = [(source, "CSV folder"), (field_mapping, "field mapping"), (template, "template")]
        if value_text:
            paths_to_check.append((Path(value_text).expanduser(), "value mapping"))
        invalid = [label for path, label in paths_to_check if not path.exists()]
        if invalid:
            messagebox.showerror("Input not found", "Could not find: " + ", ".join(invalid) + ".")
            return None
        if not source.is_dir():
            messagebox.showerror("Invalid CSV folder", "The SAP 4.7 source must be a folder.")
            return None
        if not list(source.glob("*.csv")):
            messagebox.showerror("No extracts found", "The selected source folder contains no CSV files.")
            return None
        language = self.variables["language"].get().strip() or "E"
        output = Path(self.variables["output"].get()).expanduser()
        return PipelineConfig(
            source_folder=source,
            field_mapping=field_mapping,
            value_mapping=Path(value_text).expanduser() if value_text else None,
            sap_template=template,
            output_xml=output,
            error_report=self._optional_path("error_report"),
            log_file=self._optional_path("log_file"),
            language=language,
            show_error_dialog=False,
        )

    def _optional_path(self, key: str) -> Path | None:
        value = self.variables[key].get().strip()
        return Path(value).expanduser() if value else None

    def _start(self) -> None:
        if self.running:
            return
        config = self._validate()
        if config is None:
            return
        self._set_log("")
        self.running = True
        self.run_button.configure(state="disabled")
        self.progress.start(12)
        thread = threading.Thread(target=self._run_pipeline, args=(config,), daemon=True)
        thread.start()

    def _run_pipeline(self, config: PipelineConfig) -> None:
        try:
            pipeline = MigrationPipeline(config)
            handler = QueueLogHandler(self.messages)
            handler.setFormatter(logging.Formatter("%(asctime)s  %(levelname)s  %(message)s", "%H:%M:%S"))
            pipeline.logger.addHandler(handler)
            count = pipeline.run()
            self.messages.put(("done", (config, count)))
        except Exception as exc:
            self.messages.put(("failed", exc))

    def _drain_messages(self) -> None:
        try:
            while True:
                message_type, payload = self.messages.get_nowait()
                if message_type == "log":
                    self._append_log(str(payload))
                elif message_type == "done":
                    self._finish_success(*payload)
                elif message_type == "failed":
                    self._finish_failure(payload)
        except queue.Empty:
            pass
        self.after(100, self._drain_messages)

    def _finish_success(self, config: PipelineConfig, issue_count: int) -> None:
        self._stop_running()
        report = config.error_report or config.output_xml.with_name("migration_errors.csv")
        message = f"SAP SpreadsheetML created:\n{config.output_xml}"
        if issue_count:
            message += f"\n\n{issue_count} observation(s) were collected:\n{report}"
            messagebox.showwarning("Migration completed with observations", message)
        else:
            messagebox.showinfo("Migration completed", message)

    def _finish_failure(self, error: object) -> None:
        self._stop_running()
        self._append_log(f"ERROR: {error}")
        messagebox.showerror("Migration failed", str(error))

    def _stop_running(self) -> None:
        self.running = False
        self.progress.stop()
        self.run_button.configure(state="normal")

    def _set_log(self, value: str) -> None:
        self.log_text.configure(state="normal")
        self.log_text.delete("1.0", "end")
        self.log_text.insert("end", value)
        self.log_text.configure(state="disabled")

    def _append_log(self, value: str) -> None:
        self.log_text.configure(state="normal")
        self.log_text.insert("end", value + "\n")
        self.log_text.see("end")
        self.log_text.configure(state="disabled")


def main() -> None:
    MigrationApp().mainloop()


if __name__ == "__main__":
    main()
