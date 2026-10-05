"""
Tkinter based GUI for tn-venv.

The single public entry point is :func:`launch`, which builds a
:class:`TnVenvGUI`, starts Tk's main loop, and returns when the user
closes the window.

Run from the shell as::

    python -m tn_venv_gui
    # or, after installing the project
    tn-venv-gui
"""

from __future__ import annotations

import os
import queue
import shlex
import sys
import tkinter as tk
import traceback
import webbrowser
from pathlib import Path
from tkinter import filedialog, font as tkfont, messagebox, ttk
from typing import Optional

from tn_venv import SessionResult

import tn_venv

from .python_list import list_python_candidates, probe_custom_spec
from .version import __version__
from .workers import CreateRequest, CreateWorker, LogEvent


APP_TITLE = "tn-venv-gui"
APP_PAD = 10


# ---------------------------------------------------------------- helpers


def _browse_directory(parent: tk.Misc, initial: str = "") -> str:
    """Show a native directory chooser and return the selected path."""
    chosen = filedialog.askdirectory(parent=parent, initialdir=initial or os.getcwd())
    return chosen or ""


def _browse_file(parent: tk.Misc, filetypes: list[tuple[str, str]]) -> str:
    chosen = filedialog.askopenfilename(parent=parent, filetypes=filetypes)
    return chosen or ""


def _parse_packages(raw: str) -> list[str]:
    """Parse the multi-line package widget into a clean list."""
    out: list[str] = []
    for line in raw.splitlines():
        line = line.strip()
        if line:
            out.append(line)
    return out


class _FormError(Exception):
    """Raised when the GUI form is incomplete / invalid."""


# -------------------------------------------------------------- main class


class TnVenvGUI:
    """The Tk root window for the GUI."""

    def __init__(self) -> None:
        self.root = tk.Tk()
        self.root.title(f"{APP_TITLE}  —  tn-venv {__version__}")
        self.root.geometry("880x680")
        self.root.minsize(720, 560)

        # ttk styling — give widgets some breathing room.
        style = ttk.Style(self.root)
        try:
            style.theme_use("clam")
        except tk.TclError:
            pass
        style.configure("TLabel", padding=(2, 2))
        style.configure("TCheckbutton", padding=(2, 2))
        style.configure("TLabelframe.Label", padding=(6, 4))

        self._log_queue: "queue.Queue[LogEvent]" = queue.Queue()
        self._worker: Optional[CreateWorker] = None
        self._candidates = list_python_candidates()

        self._build_widgets()
        self._refresh_python_options()
        self._update_state(running=False)

        # Periodically drain the worker queue on the main thread.
        self.root.after(80, self._drain_queue)

        # Save defaults (last used directory) to a small JSON in user dir.
        self._prefs_path = Path.home() / ".tn_venv_gui.json"
        self._load_prefs()

        self.root.protocol("WM_DELETE_WINDOW", self._on_close)

    # ----------------------------------------------------------- build UI

    def _build_widgets(self) -> None:
        outer = ttk.Frame(self.root, padding=APP_PAD)
        outer.pack(fill=tk.BOTH, expand=True)

        # top row: status + progress
        top = ttk.Frame(outer)
        top.pack(fill=tk.X)
        self.status_var = tk.StringVar(value="Idle.")
        ttk.Label(top, textvariable=self.status_var, anchor="w").pack(
            side=tk.LEFT, fill=tk.X, expand=True
        )
        self.progress = ttk.Progressbar(top, mode="determinate", maximum=1.0)
        self.progress.pack(side=tk.RIGHT, fill=tk.X, padx=(APP_PAD, 0))

        # notebook of configuration sections
        nb = ttk.Notebook(outer)
        nb.pack(fill=tk.BOTH, expand=False, pady=(APP_PAD, APP_PAD))
        self._build_basic_tab(nb)
        self._build_options_tab(nb)
        self._build_packages_tab(nb)
        self._build_about_tab(nb)

        # log area
        log_frame = ttk.LabelFrame(outer, text="Log")
        log_frame.pack(fill=tk.BOTH, expand=True)
        self.log = tk.Text(
            log_frame,
            height=14,
            wrap=tk.NONE,
            background="#1e1e1e",
            foreground="#dcdcdc",
            insertbackground="#dcdcdc",
            font=("Consolas", 10),
        )
        scroll_y = ttk.Scrollbar(log_frame, orient=tk.VERTICAL, command=self.log.yview)
        scroll_x = ttk.Scrollbar(log_frame, orient=tk.HORIZONTAL, command=self.log.xview)
        self.log.configure(yscrollcommand=scroll_y.set, xscrollcommand=scroll_x.set)
        self.log.grid(row=0, column=0, sticky="nsew")
        scroll_y.grid(row=0, column=1, sticky="ns")
        scroll_x.grid(row=1, column=0, sticky="ew")
        log_frame.rowconfigure(0, weight=1)
        log_frame.columnconfigure(0, weight=1)
        self.log.configure(state=tk.DISABLED)

        # tag-based colouring for log levels
        self.log.tag_configure("info", foreground="#9cdcfe")
        self.log.tag_configure("ok", foreground="#4ec9b0")
        self.log.tag_configure("warn", foreground="#dcdcaa")
        self.log.tag_configure("error", foreground="#f48771")
        self.log.tag_configure("debug", foreground="#808080")

        # bottom row of action buttons
        actions = ttk.Frame(outer)
        actions.pack(fill=tk.X, pady=(APP_PAD, 0))
        self.create_btn = ttk.Button(
            actions, text="Create environment", command=self._on_create
        )
        self.create_btn.pack(side=tk.LEFT)
        self.cancel_btn = ttk.Button(
            actions, text="Cancel", command=self._on_cancel
        )
        self.cancel_btn.pack(side=tk.LEFT, padx=(APP_PAD, 0))
        ttk.Button(actions, text="Clear log", command=self._clear_log).pack(
            side=tk.LEFT, padx=(APP_PAD, 0)
        )
        ttk.Button(actions, text="Quit", command=self._on_close).pack(side=tk.RIGHT)


    # -- tabs ---------------------------------------------------------------

    def _build_basic_tab(self, nb: ttk.Notebook) -> None:
        tab = ttk.Frame(nb, padding=APP_PAD)
        nb.add(tab, text="Basic")

        # destination
        ttk.Label(tab, text="Destination folder:").grid(
            row=0, column=0, sticky="w", pady=2
        )
        self.dest_var = tk.StringVar(value=str(Path(".venv").resolve()))
        dest_entry = ttk.Entry(tab, textvariable=self.dest_var)
        dest_entry.grid(row=0, column=1, sticky="ew", pady=2, padx=(APP_PAD, 4))
        ttk.Button(tab, text="Browse…", command=self._on_browse_dest).grid(
            row=0, column=2, sticky="ew", pady=2
        )

        # python interpreter dropdown
        ttk.Label(tab, text="Python interpreter:").grid(
            row=1, column=0, sticky="w", pady=2
        )
        self.python_var = tk.StringVar()
        self.python_combo = ttk.Combobox(
            tab, textvariable=self.python_var, values=[], state="readonly"
        )
        self.python_combo.grid(row=1, column=1, sticky="ew", pady=2, padx=(APP_PAD, 4))
        ttk.Button(tab, text="Refresh", command=self._refresh_python_options).grid(
            row=1, column=2, sticky="ew", pady=2
        )

        # optional custom spec / executable path
        ttk.Label(tab, text="Custom spec / path (optional):").grid(
            row=2, column=0, sticky="w", pady=2
        )
        self.custom_python_var = tk.StringVar()
        custom = ttk.Entry(tab, textvariable=self.custom_python_var)
        custom.grid(row=2, column=1, sticky="ew", pady=2, padx=(APP_PAD, 4))
        ttk.Button(tab, text="Probe", command=self._on_probe_python).grid(
            row=2, column=2, sticky="ew", pady=2
        )

        # prompt
        ttk.Label(tab, text="Prompt (optional):").grid(
            row=3, column=0, sticky="w", pady=2
        )
        self.prompt_var = tk.StringVar()
        ttk.Entry(tab, textvariable=self.prompt_var).grid(
            row=3, column=1, columnspan=2, sticky="ew", pady=2, padx=(APP_PAD, 0)
        )

        tab.columnconfigure(1, weight=1)

    def _build_options_tab(self, nb: ttk.Notebook) -> None:
        tab = ttk.Frame(nb, padding=APP_PAD)
        nb.add(tab, text="Options")

        self.var_clear = tk.BooleanVar()
        self.var_upgrade = tk.BooleanVar()
        self.var_system_site = tk.BooleanVar()
        self.var_upgrade_pip = tk.BooleanVar()
        self.var_with_pip = tk.BooleanVar(value=True)
        self.var_offline = tk.BooleanVar()

        ttk.Checkbutton(tab, text="Clear existing destination if it exists",
                        variable=self.var_clear).grid(row=0, column=0, sticky="w")
        ttk.Checkbutton(tab, text="Upgrade existing environment",
                        variable=self.var_upgrade).grid(row=1, column=0, sticky="w")
        ttk.Checkbutton(tab, text="Make system site-packages importable",
                        variable=self.var_system_site).grid(row=2, column=0, sticky="w")
        ttk.Checkbutton(tab, text="Seed pip into the environment",
                        variable=self.var_with_pip).grid(row=3, column=0, sticky="w")
        ttk.Checkbutton(tab, text="Upgrade pip after seeding",
                        variable=self.var_upgrade_pip).grid(row=4, column=0, sticky="w")
        ttk.Checkbutton(tab, text="Offline (use cached wheels only)",
                        variable=self.var_offline).grid(row=5, column=0, sticky="w")

        ttk.Separator(tab, orient=tk.HORIZONTAL).grid(
            row=6, column=0, columnspan=2, sticky="ew", pady=8
        )

        ttk.Label(tab, text="Symlinks / copies (auto on Windows):").grid(
            row=7, column=0, sticky="w", pady=2
        )
        self.link_mode = tk.StringVar(value="auto")
        rb_frame = ttk.Frame(tab)
        rb_frame.grid(row=7, column=1, sticky="w", pady=2)
        for label, value in (("Auto", "auto"), ("Symlinks", "symlinks"),
                              ("Copies", "copies")):
            ttk.Radiobutton(rb_frame, text=label, value=value,
                            variable=self.link_mode).pack(side=tk.LEFT, padx=4)

    def _build_packages_tab(self, nb: ttk.Notebook) -> None:
        tab = ttk.Frame(nb, padding=APP_PAD)
        nb.add(tab, text="Packages")

        ttk.Label(tab, text="Packages to install (one per line; e.g. "
                            "'requests==2.32.0'):").grid(row=0, column=0, sticky="w")
        self.packages_text = tk.Text(tab, height=6, wrap=tk.WORD)
        self.packages_text.grid(row=1, column=0, columnspan=3, sticky="nsew", pady=4)

        ttk.Label(tab, text="Requirements files:").grid(
            row=2, column=0, sticky="w", pady=(8, 2)
        )
        self.req_list = tk.Listbox(tab, height=4)
        self.req_list.grid(row=3, column=0, columnspan=2, sticky="nsew", pady=2)
        req_btns = ttk.Frame(tab)
        req_btns.grid(row=3, column=2, sticky="ns", padx=(APP_PAD, 0))
        ttk.Button(req_btns, text="Add…",
                   command=self._on_add_requirement).pack(fill=tk.X)
        ttk.Button(req_btns, text="Remove",
                   command=self._on_remove_requirement).pack(fill=tk.X, pady=(4, 0))

        tab.rowconfigure(1, weight=1)
        tab.rowconfigure(3, weight=1)
        tab.columnconfigure(0, weight=1)
        tab.columnconfigure(1, weight=1)

    def _build_about_tab(self, nb: ttk.Notebook) -> None:
        tab = ttk.Frame(nb, padding=APP_PAD)
        nb.add(tab, text="About")

        title_font = tkfont.Font(family="TkDefaultFont", size=14, weight="bold")
        body_font = tkfont.Font(family="TkDefaultFont", size=10)
        mono_font = tkfont.Font(family="Consolas", size=9)

        # ---- header (name + version) ----------------------------------
        header = ttk.Frame(tab)
        header.pack(fill=tk.X, anchor="w")
        ttk.Label(header, text="tn-venv-gui", font=title_font).pack(side=tk.LEFT)
        ttk.Label(
            header,
            text=f"  v{__version__}",
            foreground="#888888",
            font=body_font,
        ).pack(side=tk.LEFT, padx=(8, 0))

        ttk.Separator(tab, orient=tk.HORIZONTAL).pack(fill=tk.X, pady=(8, 12))

        # ---- description ----------------------------------------------
        desc = (
            "A graphical frontend for tn-venv.\n"
            "Built with Tkinter — runs anywhere Python's stdlib does."
        )
        ttk.Label(tab, text=desc, justify=tk.LEFT, font=body_font).pack(anchor="w")

        # ---- facts table (python / tn-venv versions) -------------------
        facts_frame = ttk.LabelFrame(tab, text="Runtime", padding=APP_PAD)
        facts_frame.pack(fill=tk.X, pady=(12, 8))
        facts = [
            ("Python", f"{sys.version_info.major}.{sys.version_info.minor}."
                       f"{sys.version_info.micro}  ({sys.executable})"),
            ("tn-venv", tn_venv.__version__),
            ("Tk", f"{tk.TkVersion} (Tcl {tk.TclVersion})"),
        ]
        for row, (key, value) in enumerate(facts):
            ttk.Label(facts_frame, text=f"{key}:", font=body_font).grid(
                row=row, column=0, sticky="w", padx=(0, 8), pady=1
            )
            ttk.Label(facts_frame, text=value, font=mono_font).grid(
                row=row, column=1, sticky="w", pady=1
            )
        facts_frame.columnconfigure(1, weight=1)

        # ---- links ----------------------------------------------------
        links_frame = ttk.Frame(tab)
        links_frame.pack(fill=tk.X, pady=(4, 8))
        url = "https://github.com/tokenoodle-everything/tn-venv-gui"
        link = ttk.Label(
            links_frame,
            text=url,
            foreground="#3a6ea5",
            cursor="hand2",
            font=body_font,
        )
        link.pack(side=tk.LEFT)
        link.bind("<Button-1>", lambda _e: webbrowser.open_new_tab(url))
        ttk.Button(
            links_frame,
            text="Open",
            width=8,
            command=lambda: webbrowser.open_new_tab(url),
        ).pack(side=tk.LEFT, padx=(8, 0))

        # ---- copy-info button ----------------------------------------
        info = (
            f"tn-venv-gui {__version__}\n"
            f"tn-venv     {tn_venv.__version__}\n"
            f"Python      {sys.version}\n"
            f"Tk          {tk.TkVersion} (Tcl {tk.TclVersion})\n"
            f"Platform    {sys.platform}\n"
        )
        btns = ttk.Frame(tab)
        btns.pack(fill=tk.X, pady=(8, 0))
        ttk.Button(
            btns,
            text="Copy debug info",
            command=lambda: self._copy_to_clipboard(info),
        ).pack(side=tk.LEFT)

    def _copy_to_clipboard(self, text: str) -> None:
        """Copy ``text`` to the OS clipboard and report success."""
        try:
            self.root.clipboard_clear()
            self.root.clipboard_append(text)
            # ``clipboard_append`` only takes effect once Tk processes
            # the update; force it so the data is available immediately
            # when the user pastes.
            self.root.update_idletasks()
            self.status_var.set("Debug info copied to clipboard.")
        except tk.TclError as exc:
            messagebox.showerror(APP_TITLE, f"Could not copy to clipboard:\n{exc}")

    # -------------------------------------------------------------- helpers

    def _refresh_python_options(self) -> None:
        try:
            self._candidates = list_python_candidates()
        except Exception as exc:  # pragma: no cover - defensive
            messagebox.showerror(APP_TITLE, f"Failed to enumerate Python:\n{exc}")
            self._candidates = []
        labels = [c.label for c in self._candidates]
        self.python_combo["values"] = labels
        if labels and not self.python_var.get():
            self.python_combo.current(0)
            self.python_var.set(labels[0])

    def _on_browse_dest(self) -> None:
        chosen = _browse_directory(
            self.root,
            initial=str(Path(self.dest_var.get() or ".").parent),
        )
        if chosen:
            self.dest_var.set(chosen)

    def _on_probe_python(self) -> None:
        spec = self.custom_python_var.get().strip()
        if not spec:
            messagebox.showinfo(APP_TITLE, "Enter a Python spec or executable path first.")
            return
        cand = probe_custom_spec(spec)
        if cand is None:
            messagebox.showerror(
                APP_TITLE,
                f"Could not resolve Python interpreter from spec:\n  {spec}",
            )
            return
        existing = list(self.python_combo["values"])
        labels = [cand.label] + [
            lbl for lbl in existing if lbl != cand.label
        ]
        self.python_combo["values"] = labels
        self.python_combo.set(cand.label)
        self.python_var.set(cand.label)

    def _on_add_requirement(self) -> None:
        path = _browse_file(
            self.root,
            filetypes=[("Requirements", "*.txt *.pip"), ("All files", "*.*")],
        )
        if path:
            self.req_list.insert(tk.END, path)

    def _on_remove_requirement(self) -> None:
        for idx in reversed(self.req_list.curselection()):
            self.req_list.delete(idx)

    def _clear_log(self) -> None:
        self.log.configure(state=tk.NORMAL)
        self.log.delete("1.0", tk.END)
        self.log.configure(state=tk.DISABLED)

    def _selected_python_specs(self) -> list[str]:
        """Resolve the chosen dropdown entry to the executable path."""
        label = self.python_var.get().strip()
        for cand in self._candidates:
            if cand.label == label:
                return [cand.spec]
        custom = self.custom_python_var.get().strip()
        if custom:
            return [custom]
        return []

    def _update_state(self, *, running: bool) -> None:
        self.create_btn.configure(state=tk.DISABLED if running else tk.NORMAL)
        self.cancel_btn.configure(state=tk.NORMAL if running else tk.DISABLED)
        if not running:
            self.progress["value"] = 0.0

    # -------------------------------------------------------------- actions

    def _on_create(self) -> None:
        if self._worker is not None and self._worker.is_alive():
            return
        try:
            request = self._gather_request()
        except _FormError as exc:
            messagebox.showerror(APP_TITLE, str(exc))
            return

        self._clear_log()
        self._log("info", f"Creating venv at {request.dest}")
        self._log("info", "Effective command line:")
        self._log(
            "info",
            "  " + " ".join(shlex.quote(part) for part in self._build_cli_preview(request)),
        )

        self._worker = CreateWorker(request, self._log_queue)
        self._worker.start()
        self._update_state(running=True)
        self.status_var.set("Working…")
        self._save_prefs()

    def _on_cancel(self) -> None:
        if self._worker is not None and self._worker.is_alive():
            self._worker.cancel()
            self._log("warn", "Cancellation requested — waiting for current step to finish.")
            self.status_var.set("Cancelling…")

    def _set_progress(self, value: float, label: str) -> None:
        self.progress["value"] = max(0.0, min(1.0, value))
        self.status_var.set(label)


    # ---------------------------------------------------------- log helpers

    def _log(self, level: str, text: str) -> None:
        """Append a coloured line directly (used by the GUI itself)."""
        self.log.configure(state=tk.NORMAL)
        tag = level if level in {"info", "ok", "warn", "error", "debug"} else "info"
        self.log.insert(tk.END, text + "\n", (tag,))
        self.log.see(tk.END)
        self.log.configure(state=tk.DISABLED)

    def _drain_queue(self) -> None:
        # Guard against the root having been torn down (smoke tests,
        # abrupt close). Tk raises TclError when scheduling after destroy.
        try:
            while True:
                event = self._log_queue.get_nowait()
                self._handle_event(event)
        except queue.Empty:
            pass
        finally:
            try:
                self.root.after(80, self._drain_queue)
            except tk.TclError:
                pass

    def _handle_event(self, event: LogEvent) -> None:
        if event.kind == "line":
            tag = "info"
            text = event.text
            lowered = text.lower()
            if "error" in lowered or "failed" in lowered or "traceback" in lowered:
                tag = "error"
            elif "warn" in lowered:
                tag = "warn"
            elif text.lstrip().startswith("ok"):
                tag = "ok"
            elif lowered.startswith("debug"):
                tag = "debug"
            self._log(tag, text)
        elif event.kind == "progress":
            value, label = event.payload
            self._set_progress(value, label)
        elif event.kind == "done":
            self._update_state(running=False)
            result: SessionResult = event.payload
            self._log("ok", "Environment created successfully.")
            self._show_result(result)
        elif event.kind == "error":
            self._update_state(running=False)
            self._log("error", event.text)
            self.status_var.set("Failed.")

    def _show_result(self, result: SessionResult) -> None:
        msg_lines = [
            "Virtual environment is ready.",
            "",
            f"env_dir      : {result.env_dir}",
            f"python       : {result.exe}",
            f"site-packages: {result.site_packages}",
        ]
        if result.activation_scripts:
            msg_lines.append("activation scripts:")
            for s in result.activation_scripts:
                msg_lines.append(f"  - {s}")
        if result.prompt:
            msg_lines.append(f"prompt       : {result.prompt}")
        msg_lines.append("")
        msg_lines.append(self._activation_hint(result))
        messagebox.showinfo(APP_TITLE, "\n".join(msg_lines))
        self.status_var.set(f"Done — {result.env_dir}")

    @staticmethod
    def _activation_hint(result: SessionResult) -> str:
        bin_path = result.env_dir / ("Scripts" if os.name == "nt" else "bin")
        if os.name == "nt":
            return (
                f"Activate with:\n  {bin_path}\\Activate.ps1  (PowerShell)\n"
                f"  {bin_path}\\activate.bat  (cmd)"
            )
        return f"Activate with:\n  source {bin_path}/activate"

    # -------------------------------------------------------------- prefs

    def _prefs_data(self) -> dict:
        return {
            "dest": self.dest_var.get(),
            "python": self.python_var.get(),
            "prompt": self.prompt_var.get(),
            "packages": self.packages_text.get("1.0", tk.END).strip(),
            "requirements": list(self.req_list.get(0, tk.END)),
        }

    def _apply_prefs(self, data: dict) -> None:
        if "dest" in data and data["dest"]:
            self.dest_var.set(data["dest"])
        if "python" in data and data["python"]:
            self.python_var.set(data["python"])
        if "prompt" in data and data["prompt"] is not None:
            self.prompt_var.set(data["prompt"])
        if "packages" in data and data["packages"]:
            self.packages_text.delete("1.0", tk.END)
            self.packages_text.insert("1.0", data["packages"])
        if "requirements" in data and data["requirements"]:
            self.req_list.delete(0, tk.END)
            for req in data["requirements"]:
                self.req_list.insert(tk.END, req)

    def _load_prefs(self) -> None:
        try:
            import json

            if self._prefs_path.is_file():
                self._apply_prefs(json.loads(self._prefs_path.read_text("utf-8")))
        except Exception:
            pass

    def _save_prefs(self) -> None:
        try:
            import json

            self._prefs_path.write_text(
                json.dumps(self._prefs_data(), indent=2), encoding="utf-8"
            )
        except Exception:
            pass

    # ---------------------------------------------------- request building

    def _gather_request(self) -> CreateRequest:
        dest_raw = self.dest_var.get().strip()
        if not dest_raw:
            raise _FormError("Please choose a destination folder.")
        dest = Path(dest_raw).expanduser()
        if not dest.is_absolute():
            dest = (Path.cwd() / dest).resolve()

        mode = self.link_mode.get()
        symlinks: Optional[bool] = None
        copies: Optional[bool] = None
        if mode == "symlinks":
            symlinks = True
        elif mode == "copies":
            copies = True

        requirements = [self.req_list.get(i) for i in range(self.req_list.size())]

        return CreateRequest(
            dest=dest,
            python=self._selected_python_specs(),
            clear=self.var_clear.get(),
            upgrade=self.var_upgrade.get(),
            system_site_packages=self.var_system_site.get(),
            symlinks=symlinks,
            copies=copies,
            with_pip=self.var_with_pip.get(),
            upgrade_pip=self.var_upgrade_pip.get(),
            offline=self.var_offline.get(),
            prompt=self.prompt_var.get().strip() or None,
            packages=_parse_packages(self.packages_text.get("1.0", tk.END)),
            requirements=requirements,
        )

    def _build_cli_preview(self, req: CreateRequest) -> list[str]:
        parts = ["tn-venv", str(req.dest)]
        if req.python:
            parts += ["--python", req.python[0]]
        if req.clear:
            parts.append("--clear")
        if req.upgrade:
            parts.append("--upgrade")
        if req.system_site_packages:
            parts.append("--system-site-packages")
        if req.symlinks is True:
            parts.append("--symlinks")
        if req.copies is True:
            parts.append("--copies")
        if not req.with_pip:
            parts.append("--without-pip")
        if req.upgrade_pip:
            parts.append("--upgrade-pip")
        if req.offline:
            parts.append("--offline")
        if req.prompt:
            parts += ["--prompt", req.prompt]
        for pkg in req.packages:
            parts += ["--pkg", pkg]
        for r in req.requirements:
            parts += ["--requirements", r]
        return parts

    # ------------------------------------------------------- lifecycle

    def mainloop(self) -> None:
        self.root.mainloop()

    def _on_close(self) -> None:
        if self._worker is not None and self._worker.is_alive():
            if not messagebox.askyesno(
                APP_TITLE,
                "A creation task is still running. Quit anyway?",
            ):
                return
            self._worker.cancel()
        self._save_prefs()
        self.root.destroy()


# ----------------------------------------------------------------- launch


def launch() -> None:
    """Build and run the GUI; blocks until the user closes the window."""
    # First-run convenience: drop a ``.pth`` so subsequent
    # ``tn-venv`` invocations advertise the ``gui`` subcommand. This
    # is silent and best-effort; users can opt out with
    # ``TN_VENV_GUI_NO_PTH=1``.
    try:
        from . import pth as _pth
        if not _pth.is_installed():
            _pth.install_pth()
    except Exception:
        pass
    try:
        TnVenvGUI().mainloop()
    except Exception:  # pragma: no cover - last-resort safety net
        traceback.print_exc()
        try:
            messagebox.showerror(
                APP_TITLE, "tn-venv-gui failed to start:\n\n" + traceback.format_exc()
            )
        except Exception:
            pass
        sys.exit(1)


if __name__ == "__main__":  # pragma: no cover
    launch()

