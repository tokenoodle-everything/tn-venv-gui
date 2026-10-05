"""
tn-venv-gui

A graphical GUI frontend built upon the tn-venv virtual environment manager.
"""

from __future__ import annotations

from .version import __version__, __version_tuple__
from .app import TnVenvGUI, launch

__all__ = [
    "__version__",
    "__version_tuple__",
    "TnVenvGUI",
    "launch",
]
