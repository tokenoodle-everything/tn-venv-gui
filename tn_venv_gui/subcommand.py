"""
Integration with the :mod:`tn_venv` CLI.

When :mod:`tn_venv_gui` is imported (or when ``tn-venv-gui`` is launched),
this module monkey-patches :func:`tn_venv.cli_run` so that ``tn-venv gui``
becomes a first-class subcommand of :mod:`tn_venv`. The default
behaviour of ``tn-venv`` is preserved unchanged.

Two entry points are exposed:

* :func:`install_subcommand` — patches :func:`tn_venv.cli_run` once. The
  function is idempotent; calling it more than once is a no-op.
* :func:`auto_install` — convenience wrapper invoked from
  :mod:`tn_venv_gui.__init__`. It calls :func:`install_subcommand` so
  the subcommand is wired up simply by ``import tn_venv_gui``.

The patch is deliberately defensive:

* it is a no-op when :mod:`tn_venv` is not importable (so the GUI can
  still be packaged for environments that don't ship :mod:`tn_venv`);
* it is a no-op when :mod:`tn_venv.cli` exposes an unexpected shape
  (so a future major release doesn't crash the GUI import);
* it always defers to the original :func:`cli_run` for every
  invocation that doesn't start with ``"gui"`` — so ``tn-venv .venv``,
  ``tn-venv --list-pythons``, etc. keep working byte-for-byte.
"""

from __future__ import annotations

import sys
from typing import Sequence

__all__ = [
    "install_subcommand",
    "auto_install",
    "is_installed",
    "subcommand_help",
]


_INSTALLED = False
_ORIGINAL_INNER_CLI_RUN = None  # type: ignore[var-annotated]


# --------------------------------------------------------------------- helpers


def _build_parser():
    """Late-bound import so this module is importable without tn_venv."""
    from tn_venv.cli import build_parser  # type: ignore[import-not-found]

    return build_parser()


def _run_original(args: Sequence[str] | None):
    """Delegate to the *real* (un-patched) inner ``cli_run``.

    This is the original ``tn_venv.cli.cli_run`` function captured at
    patch time. Going through ``tn_venv.cli_run`` (the wrapper) would
    re-enter our patch and recurse forever, because the wrapper does
    ``from .cli import cli_run as _cli_run`` on every invocation.
    """
    if _ORIGINAL_INNER_CLI_RUN is None:
        # Fallback path used by tests that import subcommand without
        # ever having installed it.
        from tn_venv import cli_run as outer  # type: ignore[import-not-found]

        return outer(list(args) if args is not None else None)
    return _ORIGINAL_INNER_CLI_RUN(list(args) if args is not None else None)


def _launch_gui(args: Sequence[str]) -> int:
    """Translate the ``tn-venv gui [...]`` argv tail into a GUI launch.

    Currently the GUI does not parse extra arguments — ``tn-venv gui``
    and ``tn-venv gui --some-flag`` both simply open the main window —
    but we keep the ``args`` for forward compatibility so that future
    versions can grow options (e.g. ``tn-venv gui --dest .venv``).
    """
    # Local import: launching the GUI pulls in tkinter. Keep that off the
    # import path of :mod:`tn_venv_gui` itself until the user actually
    # invokes the subcommand.
    from .app import launch

    # ``launch()`` blocks until the GUI window is closed, which is what
    # we want from a console script: a clean exit code of 0.
    launch()
    return 0


def subcommand_help() -> str:
    """Return the help string used by ``tn-venv gui --help``."""
    return (
        "Launch the tn-venv graphical frontend.\n"
        "\n"
        "This subcommand is provided by the optional 'tn-venv-gui' "
        "package.\n"
        "If the GUI cannot start (for example on a headless system) "
        "the\n"
        "underlying error is printed and the command exits with a "
        "non-zero\n"
        "status."
    )


# --------------------------------------------------------------------- patch


def install_subcommand() -> bool:
    """Patch :func:`tn_venv.cli.cli_run` so ``tn-venv gui [...]`` works.

    Returns ``True`` if the patch was applied (or was already applied),
    ``False`` if it could not be applied for any reason.

    The patch targets the *inner* ``cli_run`` (in :mod:`tn_venv.cli`)
    rather than the public wrapper (:func:`tn_venv.cli_run`). That
    wrapper does ``from .cli import cli_run as _cli_run`` on every
    invocation, so by patching the module attribute we automatically
    intercept both:

    * ``tn-venv`` console script → ``tn_venv.cli.main`` → wrapper →
      patched inner
    * direct ``from tn_venv import cli_run`` calls → wrapper → patched
      inner

    We never delegate back through the wrapper — that would re-enter
    our patch and recurse forever — we keep a reference to the
    pre-patch inner function and call *that* for non-GUI arguments.
    """
    global _INSTALLED, _ORIGINAL_INNER_CLI_RUN

    if _INSTALLED:
        return True

    try:
        from tn_venv import cli as _tn_venv_cli  # type: ignore[import-not-found]
    except Exception:
        return False

    original_inner = _tn_venv_cli.cli_run
    if getattr(original_inner, "_tn_venv_gui_patched", False):
        # Already wrapped (e.g. another import path that got there
        # first). Re-use its state.
        _INSTALLED = True
        _ORIGINAL_INNER_CLI_RUN = original_inner
        return True

    _ORIGINAL_INNER_CLI_RUN = original_inner

    def _patched(args=None, **kwargs):
        # ``cli_run`` accepts an optional ``args`` list. When called as
        # ``tn-venv gui ...`` the shell entry point hands us the full
        # argv tail, so ``args[0]`` is ``"gui"``.
        argv = list(args) if args is not None else sys.argv[1:]
        if argv and argv[0] == "gui":
            return _launch_gui(argv[1:])
        # Defer to the original inner ``cli_run`` directly — *not* via
        # the wrapper — to avoid re-entering ourselves.
        return _ORIGINAL_INNER_CLI_RUN(args, **kwargs)  # type: ignore[misc]

    _patched._tn_venv_gui_patched = True  # type: ignore[attr-defined]

    # Replace the inner function in the cli module. The next call from
    # the wrapper (``from .cli import cli_run as _cli_run``) picks up
    # this new function automatically.
    _tn_venv_cli.cli_run = _patched  # type: ignore[attr-defined]

    _INSTALLED = True
    return True


def is_installed() -> bool:
    """Return ``True`` if :func:`install_subcommand` has run successfully."""
    return _INSTALLED


def auto_install() -> bool:
    """Install the subcommand unless it has been explicitly disabled.

    The installation can be suppressed by setting the environment
    variable ``TN_VENV_GUI_NO_AUTOLOAD=1`` — useful for users that want
    to keep ``tn-venv`` untouched.
    """
    if os_environ_no_autoload():
        return False
    return install_subcommand()


def os_environ_no_autoload() -> bool:
    import os

    return bool(os.environ.get("TN_VENV_GUI_NO_AUTOLOAD"))
