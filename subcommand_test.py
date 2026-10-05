"""Tests for the ``tn-venv gui`` subcommand integration.

Runs three scenarios:

1. ``tn-venv --list-pythons`` — original tn-venv behaviour, must be
   preserved bit-for-bit.
2. ``tn-venv .venv --dry-run`` — original tn-venv behaviour with
   options, must still work.
3. ``tn-venv gui`` — must dispatch into our GUI launcher (stubbed here
   so we don't open a real window).
"""

from __future__ import annotations

import io
import sys
from contextlib import redirect_stdout


def test_original_list_pythons() -> None:
    from tn_venv import cli_run  # patched
    buf = io.StringIO()
    with redirect_stdout(buf):
        rc = cli_run(["--list-pythons", "--no-color"])
    output = buf.getvalue()
    assert rc == 0, f"expected 0, got {rc}"
    assert "cpython" in output or "no interpreters" in output, (
        f"--list-pythons didn't produce its expected output:\n{output}"
    )
    print("[1/3] --list-pythons preserved: OK")


def test_original_dry_run() -> None:
    from tn_venv import cli_run  # patched
    buf = io.StringIO()
    with redirect_stdout(buf):
        rc = cli_run([".venv-test-dry", "--dry-run", "--no-color"])
    output = buf.getvalue()
    assert rc == 0, f"expected 0, got {rc}"
    assert "dry run" in output.lower() or "resolved" in output.lower(), (
        f"--dry-run didn't produce its expected output:\n{output}"
    )
    print("[2/3] --dry-run preserved:    OK")


def test_gui_subcommand_dispatched() -> None:
    # Stub the launch() so we don't open a Tk window.
    from tn_venv_gui import app as app_module

    calls: list[tuple] = []

    def fake_launch() -> None:
        calls.append("launch")

    app_module.launch = fake_launch  # type: ignore[assignment]
    # Re-inject into subcommand so it picks up the stub.
    from tn_venv_gui import subcommand

    subcommand._launch_gui = lambda args: calls.append(("gui", tuple(args))) or 0  # type: ignore[assignment]

    # The patched cli_run is what tn-venv's main() calls.
    from tn_venv import cli_run  # patched
    rc = cli_run(["gui"])
    assert rc == 0
    assert calls and calls[0] == ("gui", ()), f"expected ('gui', ()) call, got {calls!r}"
    print("[3/3] tn-venv gui dispatched:  OK")


def main() -> int:
    # Ensure subcommand is installed even if a prior test scrubbed it.
    import tn_venv_gui  # triggers auto_install
    from tn_venv_gui import subcommand

    subcommand.install_subcommand()

    test_original_list_pythons()
    test_original_dry_run()
    test_gui_subcommand_dispatched()
    print("ALL OK")
    return 0


if __name__ == "__main__":
    sys.exit(main())
