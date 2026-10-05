"""Headless smoke test for tn_venv_gui.

Runs the GUI in a virtual display so we can drive ``_on_create``
programmatically and assert that the worker calls into ``tn_venv``
and reports a :class:`SessionResult`.
"""

from __future__ import annotations

import os
import queue
import sys
import tempfile
import time
import tkinter as tk

from tn_venv_gui.app import TnVenvGUI
from tn_venv_gui.workers import LogEvent


def _wait_for_done(app: TnVenvGUI, timeout: float = 120.0) -> list[LogEvent]:
    deadline = time.time() + timeout
    captured: list[LogEvent] = []
    done_seen = False
    while time.time() < deadline:
        try:
            while True:
                event = app._log_queue.get_nowait()
                captured.append(event)
                app._handle_event(event)
                if event.kind in {"done", "error"}:
                    done_seen = True
        except queue.Empty:
            pass
        app.root.update_idletasks()
        app.root.update()
        if done_seen:
            # Give the worker thread one more tick so its trailing
            # ``stream.flush()`` puts are drained into ``captured``.
            time.sleep(0.1)
            try:
                while True:
                    event = app._log_queue.get_nowait()
                    captured.append(event)
                    app._handle_event(event)
            except queue.Empty:
                pass
            return captured
        time.sleep(0.05)
    raise TimeoutError("Worker did not finish in time")


def main() -> int:
    app = TnVenvGUI()
    # In headless mode we don't want a modal popup to block the test.
    app._show_result = lambda result: None  # type: ignore[assignment]
    try:
        with tempfile.TemporaryDirectory() as td:
            target = os.path.join(td, "smoke-venv")
            app.dest_var.set(target)
            # Make sure there's a Python selected
            if not app.python_var.get():
                app._refresh_python_options()
            # Seed a tiny preinstalled package so we exercise the pip path.
            app.packages_text.delete("1.0", tk.END)
            app.packages_text.insert("1.0", "six==1.16.0")
            # Drain any leftover events so the assertion below sees only
            # the run we're about to perform.
            try:
                while True:
                    app._log_queue.get_nowait()
            except queue.Empty:
                pass
            app._on_create()

            captured = _wait_for_done(app)
            kinds = [e.kind for e in captured]
            print(f"--- captured events: {kinds}")
            for ev in captured:
                print(f"  [{ev.kind}] {ev.text!r}")
            errs = [e.text for e in captured if e.kind == "error"]
            assert "done" in kinds, f"Worker did not finish cleanly: {kinds} -- errors: {errs}"
            done_events = [e for e in captured if e.kind == "done"]
            result = done_events[0].payload
            print("env_dir      :", result.env_dir)
            print("python       :", result.exe)
            print("bin_path     :", result.bin_path)
            assert os.path.isdir(result.env_dir), "env_dir missing"
            assert os.path.isfile(result.exe), "python exe missing"
            assert os.path.isdir(result.bin_path), "bin_path missing"

            # Sanity-check the log contains expected output
            lines = [e.text for e in captured if e.kind == "line"]
            joined = "\n".join(lines)
            assert "ready" in joined.lower(), \
                f"Reporter output did not include ready message; got:\n{joined!r}"
            assert "pip" in joined.lower(), \
                f"pip install messages not surfaced; got:\n{joined!r}"
            # The seeded package should be importable inside the venv.
            assert result.seed is not None, "seed result missing"
            assert any("six" in p for p in result.seed.packages), \
                f"seed packages missing six: {result.seed.packages}"
            print(f"--- captured {len(lines)} log lines ---")
            print(joined)

        print("SMOKE TEST PASSED")
        return 0
    finally:
        try:
            app.root.destroy()
        except tk.TclError:
            pass
        # Let the interpreter finalize any pending TCL callbacks cleanly.
        import gc
        gc.collect()


if __name__ == "__main__":
    sys.exit(main())
