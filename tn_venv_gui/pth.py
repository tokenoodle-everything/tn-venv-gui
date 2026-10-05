"""
``.pth`` file management for transparent subcommand activation.

Python looks for ``*.pth`` files in every directory on ``sys.path`` at
interpreter startup. Each non-comment, non-blank line of a ``.pth`` is
executed with ``exec()``. We install a tiny ``.pth`` file under
``site-packages`` that does ``import tn_venv_gui`` so the GUI's
subcommand patch runs *before* any user code touches ``tn_venv``.

That makes the integration truly zero-config:

* after ``pip install tn-venv-gui``, ``tn-venv --help`` immediately
  advertises the ``gui`` subcommand;
* ``pip uninstall tn-venv-gui`` removes the ``.pth`` file as part of
  the uninstall, so there is nothing to clean up.

The file is *not* placed in the package directory itself — it lives
next to the package's dist-info folder so the uninstaller sees it.
"""

from __future__ import annotations

import os
import site
import sys
from pathlib import Path

__all__ = ["install_pth", "uninstall_pth", "pth_path", "is_installed"]

#: Name of the ``.pth`` file we drop. Leading underscore puts it first
#: alphabetically and is a convention used by several packages to make
#: their auto-loading obvious in a directory listing.
_PTH_FILENAME = "_tn_venv_gui.pth"

#: Content we write into the ``.pth``. ``import`` is enough — the
#: package's ``__init__`` already calls :func:`auto_install`.
_PTH_CONTENT = (
    "# Auto-installed by tn-venv-gui. Loads the optional subcommand\n"
    "# so that `tn-venv --help` advertises `tn-venv gui`. Safe to\n"
    "# delete: `pip uninstall tn-venv-gui` removes this file.\n"
    "import tn_venv_gui\n"
)


def _sitepackages_dir() -> Path:
    """Return the canonical site-packages directory for this interpreter.

    We always use ``sys.prefix/Lib/site-packages`` (or the POSIX
    equivalent). This is the directory where ``pip install`` puts
    packages and where ``site.addpackage`` scans for ``.pth`` files.
    Returning the *raw* ``getsitepackages()[0]`` is unreliable: in a
    venv that entry is the venv root (``<venv>``) rather than the
    site-packages subdirectory, so a ``.pth`` placed there would
    execute before ``sys.path`` includes ``<venv>/Lib/site-packages``
    — which is exactly the situation that makes ``import
    tn_venv_gui`` fail with ``ModuleNotFoundError``.
    """
    if os.name == "nt":
        candidate = Path(sys.prefix) / "Lib" / "site-packages"
    else:
        candidate = Path(sys.prefix) / "lib" / (
            f"python{sys.version_info.major}.{sys.version_info.minor}"
            f"-{'x86_64' if sys.maxsize > 2**32 else 'i386'}"
            if sys.platform == "darwin"
            else f"python{sys.version_info.major}.{sys.version_info.minor}"
        ) / "site-packages"
    # Verify it actually exists; if not, fall back to the legacy
    # ``getsitepackages`` hint which may include the right path even
    # when our heuristic fails (e.g. unusual layouts).
    if candidate.is_dir():
        return candidate
    try:
        for hint in site.getsitepackages():
            p = Path(hint)
            # The venv root (``getsitepackages()[0]``) is *not* what we
            # want; pick the deepest one that contains the package.
            if p.is_dir() and (p / "tn_venv_gui" / "__init__.py").is_file():
                return p
    except Exception:
        pass
    return candidate


def pth_path() -> Path:
    """Return the ``.pth`` path that would be (or has been) installed."""
    return _sitepackages_dir() / _PTH_FILENAME


def is_installed() -> bool:
    """Return ``True`` if our ``.pth`` file is currently present."""
    p = pth_path()
    if not p.is_file():
        return False
    try:
        return "import tn_venv_gui" in p.read_text(encoding="utf-8")
    except OSError:
        return False


def install_pth(*, overwrite: bool = True) -> Path | None:
    """Drop the ``.pth`` file. Returns the path, or ``None`` on failure.

    * ``overwrite=True`` (default) replaces any existing file with
      the same name (the typical case after an upgrade).
    * ``overwrite=False`` is a no-op when the file already exists.

    The directory is created on demand. A ``TN_VENV_GUI_NO_PTH=1``
    environment variable forces this function to return ``None`` so
    power users can opt out.
    """
    if os.environ.get("TN_VENV_GUI_NO_PTH"):
        return None

    target = pth_path()
    if target.is_file() and not overwrite:
        return target
    try:
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(_PTH_CONTENT, encoding="utf-8")
    except OSError:
        return None
    return target


def uninstall_pth() -> bool:
    """Remove the ``.pth`` file if it belongs to us. Returns ``True`` on removal."""
    target = pth_path()
    if not target.is_file():
        return False
    try:
        text = target.read_text(encoding="utf-8")
    except OSError:
        return False
    if "import tn_venv_gui" not in text:
        # Not ours; leave it alone.
        return False
    try:
        target.unlink()
    except OSError:
        return False
    return True
