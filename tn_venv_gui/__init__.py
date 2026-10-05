"""
tn-venv-gui

A graphical GUI frontend built upon the tn-venv virtual environment manager.
"""

from __future__ import annotations

from .version import __version__, __version_tuple__
from .app import TnVenvGUI, launch

# Register the optional ``tn-venv gui`` subcommand on import.
# The hook is a no-op when ``tn_venv`` is unavailable and can be
# suppressed by setting ``TN_VENV_GUI_NO_AUTOLOAD=1`` in the
# environment. Importing :mod:`tn_venv_gui` is therefore always safe.
from . import subcommand as _subcommand  # noqa: F401  (re-exported)

_subcommand.auto_install()

__all__ = [
    "__version__",
    "__version_tuple__",
    "TnVenvGUI",
    "launch",
]
