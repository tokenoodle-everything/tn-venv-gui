"""
Background workers that drive :func:`tn_venv.create_venv` from the GUI.

The workers run on a daemon thread and stream ``tn_venv``'s ``Reporter``
output to the Tk main loop through a thread-safe queue. This keeps the
UI responsive while the (potentially slow) ``pip install`` step runs.
"""

from __future__ import annotations

import queue
import threading
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from tn_venv import SessionResult
from tn_venv.errors import TnVenvError
from tn_venv.report import Reporter
from tn_venv.session import Options, run_session


# ------------------------------------------------------------------ log pipe


class QueueStream:
    """File-like adapter that pushes each ``write()`` into a ``queue.Queue``.

    ``tn_venv``'s :class:`Reporter` calls ``stream.write(text)`` whenever it
    has something to print. We forward those writes — line by line — to the
    Tk thread so they can be appended to a ``ScrolledText`` widget without
    blocking the worker.
    """

    def __init__(self, q: "queue.Queue[LogEvent]") -> None:
        self._q = q
        self._buffer = ""

    def write(self, text: str) -> int:  # noqa: D401 - file-like protocol
        if not text:
            return 0
        self._buffer += text
        while "\n" in self._buffer:
            line, _, self._buffer = self._buffer.partition("\n")
            if line:
                self._q.put(LogEvent(kind="line", text=line))
        return len(text)

    # print() in Python also consults ``isatty`` and ``writelines``; we don't
    # need them, but providing ``isatty`` returning False keeps Reporter's
    # color detection honest.
    def isatty(self) -> bool:
        return False

    def flush(self) -> None:  # noqa: D401 - file-like protocol
        if self._buffer:
            self._q.put(LogEvent(kind="line", text=self._buffer))
            self._buffer = ""


@dataclass
class LogEvent:
    kind: str  # "line" | "done" | "error" | "progress"
    text: str = ""
    payload: Any = None


# --------------------------------------------------------------- options DTO


@dataclass
class CreateRequest:
    """User inputs from the GUI form, ready to feed ``create_venv``."""

    dest: Path
    python: list[str]
    clear: bool
    upgrade: bool
    system_site_packages: bool
    symlinks: bool | None
    copies: bool | None
    with_pip: bool
    upgrade_pip: bool
    offline: bool
    prompt: str | None
    packages: list[str]
    requirements: list[str]


# ------------------------------------------------------------------- worker


class CreateWorker(threading.Thread):
    """Run :func:`create_venv` on a daemon thread.

    The worker consumes a :class:`CreateRequest`, attaches a custom
    :class:`Reporter` whose stream is a :class:`QueueStream`, and reports
    completion through the same queue.
    """

    def __init__(
        self,
        request: CreateRequest,
        q: "queue.Queue[LogEvent]",
    ) -> None:
        super().__init__(daemon=True, name="TnVenvGUI-CreateWorker")
        self._request = request
        self._queue = q
        self._cancel = threading.Event()
        self.result: SessionResult | None = None

    def cancel(self) -> None:
        """Best-effort cancel. ``create_venv`` is synchronous, so we can
        only short-circuit pip via flags; we set the event so callers can
        react once the call returns."""
        self._cancel.set()

    @property
    def cancelled(self) -> bool:
        return self._cancel.is_set()

    def run(self) -> None:
        stream = QueueStream(self._queue)
        # ``verbosity=2`` makes the Reporter emit step/ok/info lines.
        reporter = Reporter(verbosity=2, color=False, stream=stream)
        try:
            self._queue.put(LogEvent(kind="progress", payload=(0.05, "Starting…")))
            # Mirror the preamble that ``tn-venv``'s CLI prints before
            # delegating to ``run_session``; that way the GUI log shows
            # the destination and the interpreter being used.
            self._queue.put(
                LogEvent(
                    kind="line",
                    text=f"==> creating virtual environment at {self._request.dest}",
                )
            )
            # ``create_venv`` builds its own reporter (and would discard
            # ours); bypass it and drive ``run_session`` directly so the
            # GUI receives every line.
            options = Options.from_mapping(
                {
                    "dest": self._request.dest,
                    "python": self._request.python,
                    "clear": self._request.clear,
                    "upgrade": self._request.upgrade,
                    "system_site_packages": self._request.system_site_packages,
                    "symlinks": self._request.symlinks,
                    "copies": self._request.copies,
                    "seeder": "pip" if self._request.with_pip else "none",
                    "no_pip": not self._request.with_pip,
                    "upgrade_pip": self._request.upgrade_pip,
                    "offline": self._request.offline,
                    "prompt": self._request.prompt,
                    "seed_packages": self._request.packages,
                    "requirements": self._request.requirements,
                    "verbose": 1,
                }
            )
            self.result = run_session(options, reporter)
            stream.flush()
            self._queue.put(LogEvent(kind="progress", payload=(1.0, "Done")))
            self._queue.put(LogEvent(kind="done", payload=self.result))
        except TnVenvError as exc:
            stream.flush()
            self._queue.put(LogEvent(kind="error", text=str(exc)))
        except Exception as exc:  # pragma: no cover - defensive
            stream.flush()
            import traceback as _tb
            self._queue.put(
                LogEvent(kind="error", text=f"unexpected: {exc!r}\n{_tb.format_exc()}")
            )
