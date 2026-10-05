"""Tests for the ``tn-venv gui`` subcommand integration.

Runs several scenarios:

1. ``tn-venv --list-pythons`` — original tn-venv behaviour, must be
   preserved bit-for-bit.
2. ``tn-venv .venv --dry-run`` — original tn-venv behaviour with
   options, must still work.
3. ``tn-venv gui`` — must dispatch into our GUI launcher (stubbed here
   so we don't open a real window).
4. ``tn-venv gui --help`` — must print our subcommand help, not
   argparse's "unrecognised arguments" error.
5. ``tn-venv help gui`` — alias for the same help text.
6. ``tn-venv --help`` — must advertise the subcommand in the epilog.
7. ``tn-venv help`` (no argument) — must NOT swallow the tn-venv help
   handler.
"""

from __future__ import annotations

import io
import sys
from contextlib import redirect_stdout


def _stub_launch() -> list[tuple]:
    """Stub the actual GUI ``launch()`` so no window is opened.

    We stub ``tn_venv_gui.app.launch`` (which ``_launch_gui`` calls
    after handling ``--help``) so the rest of the subcommand logic —
    help printing, banner, error wrapping — remains exercisable.
    """
    from tn_venv_gui import app as app_module

    calls: list[tuple] = []

    def fake_launch() -> None:
        calls.append(("launch",))

    app_module.launch = fake_launch  # type: ignore[assignment]
    return calls


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
    print("[1/7] --list-pythons preserved: OK")


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
    print("[2/7] --dry-run preserved:    OK")


def test_gui_subcommand_dispatched() -> None:
    calls = _stub_launch()
    from tn_venv import cli_run  # patched
    rc = cli_run(["gui"])
    assert rc == 0
    assert calls and calls[0] == ("launch",), (
        f"expected ('launch',) call, got {calls!r}"
    )
    print("[3/7] tn-venv gui dispatched:  OK")


def test_gui_subcommand_help() -> None:
    calls = _stub_launch()
    from tn_venv import cli_run  # patched
    buf = io.StringIO()
    with redirect_stdout(buf):
        rc = cli_run(["gui", "--help"])
    output = buf.getvalue()
    assert rc == 0, f"expected 0, got {rc}"
    assert "Launch the tn-venv graphical frontend" in output, (
        f"gui --help missing the description:\n{output}"
    )
    assert "TN_VENV_GUI_NO_AUTOLOAD" in output, (
        f"gui --help didn't mention TN_VENV_GUI_NO_AUTOLOAD:\n{output}"
    )
    # Crucially: GUI must NOT have been launched.
    assert calls == [], f"GUI was launched unexpectedly: {calls!r}"
    print("[4/7] tn-venv gui --help:      OK")


def test_help_alias() -> None:
    calls = _stub_launch()
    from tn_venv import cli_run  # patched
    buf = io.StringIO()
    with redirect_stdout(buf):
        rc = cli_run(["help", "gui"])
    output = buf.getvalue()
    assert rc == 0, f"expected 0, got {rc}"
    assert "Launch the tn-venv graphical frontend" in output, (
        f"tn-venv help gui missing the description:\n{output}"
    )
    assert calls == [], f"GUI was launched unexpectedly: {calls!r}"
    print("[5/7] tn-venv help gui:        OK")


def test_parent_help_epilog() -> None:
    from tn_venv import cli_run  # patched
    buf = io.StringIO()
    with redirect_stdout(buf):
        # argparse exits on --help so we expect SystemExit(0).
        try:
            cli_run(["--help"])
        except SystemExit as exc:
            assert exc.code == 0, f"--help should exit 0, got {exc.code}"
    output = buf.getvalue()
    assert "optional subcommands provided by plugins" in output, (
        f"parent --help epilog missing plugin section:\n{output[-2000:]}"
    )
    assert "gui    launch the tn-venv-gui graphical frontend" in output, (
        f"parent --help doesn't list the gui subcommand:\n{output[-2000:]}"
    )
    print("[6/7] tn-venv --help epilog:   OK")


def test_help_without_subcommand_does_not_swallow() -> None:
    """``tn-venv help`` (no second arg) must not print our gui help."""
    calls = _stub_launch()
    from tn_venv import cli_run  # patched
    buf = io.StringIO()
    with redirect_stdout(buf):
        try:
            cli_run(["help"])
        except SystemExit:
            pass
    output = buf.getvalue()
    assert "Launch the tn-venv graphical frontend" not in output, (
        f"'tn-venv help' unexpectedly showed gui subcommand help:\n{output}"
    )
    assert calls == [], f"GUI was launched unexpectedly: {calls!r}"
    print("[7/7] tn-venv help (no arg):   OK")


def main() -> int:
    import tn_venv_gui  # triggers auto_install
    from tn_venv_gui import subcommand

    subcommand.install_subcommand()

    test_original_list_pythons()
    test_original_dry_run()
    test_gui_subcommand_dispatched()
    test_gui_subcommand_help()
    test_help_alias()
    test_parent_help_epilog()
    test_help_without_subcommand_does_not_swallow()
    print("ALL OK")
    return 0


if __name__ == "__main__":
    sys.exit(main())
