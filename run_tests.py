"""Run the full test suite for tn-venv-gui.

Two test scripts are exercised:

* ``subcommand_test.py`` — verifies the ``tn-venv gui`` subcommand
  integration without breaking the original tn-venv CLI. Headless-safe
  (never opens a Tk window).
* ``smoke_test.py`` — drives the GUI end-to-end and asserts a real
  venv is created. Needs a display (real or virtual).

Each script is invoked as a subprocess so its Tk resources are
released between the two runs.

Display handling
---------------

``smoke_test.py`` is skipped automatically when:

* the current platform is non-Windows/macOS (i.e. Linux) **and**
* no usable display can be found via ``$DISPLAY`` **and**
* neither the ``xvfb-run`` command nor the ``pyvirtualdisplay``
  Python package is available to provide one.

The script prints a single ``[SKIP]`` line in that case and the
overall test run still exits 0.
"""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
from pathlib import Path


def _run(cmd: list[str]) -> int:
    name = cmd[-1]
    print(f"\n==== {name} ====")
    return subprocess.run(cmd, check=False).returncode


def _has_display() -> bool:
    """``True`` if the current process already has a usable display."""
    if sys.platform.startswith("win") or sys.platform == "darwin":
        # Tk uses the native window manager on these platforms; no
        # extra setup is needed and ``$DISPLAY`` is meaningless.
        return True
    return bool(os.environ.get("DISPLAY"))


def _xvfb_run_command(child: list[str]) -> list[str] | None:
    """If ``xvfb-run`` is on PATH, wrap *child* with it; else return None."""
    xvfb = shutil.which("xvfb-run")
    if not xvfb:
        return None
    return [xvfb, "-a", *child]


def _pyvirtualdisplay_setup() -> bool:
    """Try to start a virtual display via ``pyvirtualdisplay``.

    Returns ``True`` on success and ``False`` if the package is
    unavailable or ``Xvfb`` is not installed on the system. When
    ``True`` is returned the calling test process will find
    ``$DISPLAY`` set to a working value.
    """
    try:
        from pyvirtualdisplay import Display  # type: ignore[import-not-found]
    except Exception:
        return False
    try:
        disp = Display(visible=False, size=(1024, 768))
    except Exception:
        return False
    disp.start()
    # Keep the display alive for the duration of the test process by
    # stashing it on ``os.environ`` (the test subprocess inherits
    # only env, not Python objects, but we *do* want ``$DISPLAY`` set,
    # which the ``start()`` above already does).
    os.environ["_PYVIRTUALDISPLAY"] = "1"
    return True


def main() -> int:
    here = Path(__file__).parent
    py = sys.executable

    rc = _run([py, str(here / "subcommand_test.py")])
    if rc != 0:
        return rc

    # -- smoke_test: needs a display ----------------------------------------
    smoke = [py, str(here / "smoke_test.py")]

    if _has_display():
        smoke_rc = _run(smoke)
        if smoke_rc != 0:
            return smoke_rc
    else:
        # Linux without $DISPLAY — try xvfb-run first, then
        # pyvirtualdisplay, then skip.
        wrapped = _xvfb_run_command(smoke)
        if wrapped is not None:
            print(f"\n==== {smoke[-1]} (under xvfb-run) ====")
            rc = subprocess.run(wrapped, check=False).returncode
            if rc != 0:
                return rc
        else:
            # Boot a virtual display in *this* process, then run the
            # test as a subprocess — it will inherit ``$DISPLAY``.
            old_display = os.environ.get("DISPLAY")
            try:
                if _pyvirtualdisplay_setup():
                    print(
                        f"\n==== {smoke[-1]} (under pyvirtualdisplay) ===="
                    )
                    rc = subprocess.run(smoke, check=False).returncode
                    if rc != 0:
                        return rc
                else:
                    print(
                        "[SKIP] smoke_test needs a display; neither "
                        "$DISPLAY nor xvfb-run / pyvirtualdisplay is "
                        "available. Install xvfb (apt-get install "
                        "xvfb) or 'pip install pyvirtualdisplay' to "
                        "enable the GUI smoke test."
                    )
            finally:
                if old_display is None:
                    os.environ.pop("DISPLAY", None)
                else:
                    os.environ["DISPLAY"] = old_display

    print("\nALL TEST SUITES PASSED")
    return 0


if __name__ == "__main__":
    sys.exit(main())
