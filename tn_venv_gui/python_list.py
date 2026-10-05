"""
Enumerate Python interpreters available on the system using tn-venv's
discovery machinery.

We probe a small set of common version specs; for each spec that resolves
we collect a ``(label, spec)`` tuple where ``spec`` is the value accepted
by :func:`tn_venv.create_venv` (``python=``).
"""

from __future__ import annotations

import shutil
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

from tn_venv.discovery import discover
from tn_venv.errors import DiscoverError, InterpreterNotFoundError


# A pragmatic set of version specs. ``tn_venv`` understands anything that
# ``py Launcher`` / PEP 394 understands (``python3``, ``python3.12`` …) as
# well as full executable paths. We probe what is likely installed and
# then de-duplicate by absolute path.
DEFAULT_SPECS: tuple[str, ...] = (
    "python",
    "python3",
    f"python{sys.version_info.major}",
    f"python{sys.version_info.major}.{sys.version_info.minor}",
)


@dataclass(frozen=True)
class PythonCandidate:
    """An interpreter available on the host."""

    label: str
    spec: str

    def __str__(self) -> str:  # pragma: no cover - trivial
        return self.label


def _label_for(info) -> str:
    """Build a human friendly label from a ``PythonInfo`` instance."""
    version = ".".join(str(p) for p in info.version_info[:3])
    bits = "{impl}-{ver}-{bits}".format(
        impl=info.implementation or "python",
        ver=version,
        bits=info.machine or "?",
    )
    return f"{bits}  ({info.executable})"


def list_python_candidates(
    extra_specs: Iterable[str] = (),
    *,
    include_current: bool = True,
) -> list[PythonCandidate]:
    """Return all interpreters we can resolve.

    The returned list is deduplicated by absolute path and sorted with the
    highest-version entries first. ``extra_specs`` lets the GUI forward
    additional hints the user typed themselves.
    """
    seen: dict[str, PythonCandidate] = {}

    specs = list(DEFAULT_SPECS)
    if include_current:
        specs.insert(0, sys.executable)
    specs.extend(extra_specs)

    for spec in specs:
        try:
            info = discover([spec])
        except InterpreterNotFoundError:
            continue
        except DiscoverError:
            continue
        except Exception:  # pragma: no cover - defensive
            continue
        key = str(Path(info.executable).resolve())
        if key in seen:
            continue
        seen[key] = PythonCandidate(label=_label_for(info), spec=info.executable)

    # Stable sort: newest version first, then by path for determinism.
    def _sort_key(c: PythonCandidate):
        try:
            info = discover([c.spec])
            version = tuple(info.version_info[:3])
        except Exception:
            version = (0, 0, 0)
        return (-version[0], -version[1], -version[2], c.spec.lower())

    return sorted(seen.values(), key=_sort_key)


def python_on_path() -> str | None:
    """Return ``shutil.which("python")`` or ``None``."""
    return shutil.which("python") or shutil.which("python3")


def probe_custom_spec(spec: str) -> PythonCandidate | None:
    """Resolve a single user-supplied spec (``python3.11`` or a path).

    Returns ``None`` when the interpreter cannot be located so the caller
    can surface a friendly error in the GUI.
    """
    try:
        info = discover([spec])
    except (InterpreterNotFoundError, DiscoverError):
        return None
    except Exception:
        return None
    return PythonCandidate(label=_label_for(info), spec=info.executable)


def version_from_executable(executable: str) -> str | None:
    """Best-effort version probe for the GUI; ``None`` if it fails."""
    try:
        out = subprocess.check_output(
            [executable, "-c", "import sys; print('.'.join(map(str, sys.version_info[:3])))"],
            stderr=subprocess.STDOUT,
            timeout=5,
        )
        return out.decode("utf-8", errors="replace").strip() or None
    except Exception:
        return None
