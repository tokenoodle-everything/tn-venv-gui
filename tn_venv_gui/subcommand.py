"""
Integration with the :mod:`tn_venv` CLI.

When :mod:`tn_venv_gui` is imported (or when ``tn-venv-gui`` is launched),
this module monkey-patches :func:`tn_venv.cli_run` so that ``tn-venv gui``
becomes a first-class subcommand of :mod:`tn_venv`. The default
behaviour of ``tn-venv`` is preserved unchanged.

In addition to dispatching the subcommand, this module:

* extends the ``tn-venv --help`` epilog with a section listing every
  subcommand contributed by plugins (``Optional subcommands provided
  by plugins:``), so users discover the GUI without reading our docs;
* handles ``tn-venv gui --help`` (and the alias ``tn-venv help gui``)
  by printing a dedicated help text instead of argparse's "unrecognised
  arguments" error;
* prints a short banner when the subcommand is invoked with no
  arguments, so users running it from a terminal see what happened.

Two entry points are exposed:

* :func:`install_subcommand` — patches :func:`tn_venv.cli_run` once.
  The function is idempotent; calling it more than once is a no-op.
* :func:`auto_install` — convenience wrapper invoked from
  :mod:`tn_venv_gui.__init__`. It calls :func:`install_subcommand` so
  the subcommand is wired up simply by ``import tn_venv_gui``.

The patch is deliberately defensive:

* it is a no-op when :mod:`tn_venv` is not importable (so the GUI can
  still be packaged for environments that don't ship :mod:`tn_venv`);
* it is a no-op when :mod:`tn_venv.cli` exposes an unexpected shape
  (so a future major release doesn't crash the GUI import);
* it always defers to the original :func:`cli_run` for every
  invocation that doesn't start with one of the registered
  subcommands — so ``tn-venv .venv``, ``tn-venv --list-pythons``,
  etc. keep working byte-for-byte.
"""

from __future__ import annotations

import argparse
import sys
from dataclasses import dataclass
from typing import Sequence

__all__ = [
    "install_subcommand",
    "auto_install",
    "is_installed",
    "subcommand_help",
    "list_subcommands",
]


# --------------------------------------------------------------------- metadata


@dataclass(frozen=True)
class SubcommandSpec:
    """Description of a subcommand contributed by this package."""

    name: str           # the argv token (e.g. ``"gui"``)
    short: str          # one-line description used in the parent help
    help: str           # long description used by ``<subcommand> --help``
    package: str        # owning package, shown in the help epilog


# Single source of truth for what we contribute. Adding more
# subcommands later is purely additive: drop a new entry in here and
# both ``tn-venv --help`` and ``tn-venv help <subcommand>`` pick it up.
SUBCOMMANDS: dict[str, SubcommandSpec] = {
    "gui": SubcommandSpec(
        name="gui",
        short="launch the tn-venv-gui graphical frontend",
        help=(
            "Launch the tn-venv graphical frontend.\n"
            "\n"
            "This subcommand is provided by the optional 'tn-venv-gui' "
            "package\n"
            "(https://github.com/tokenoodle-everything/tn-venv-gui). "
            "It opens\n"
            "a Tkinter window with the same options exposed by the "
            "``tn-venv-gui``\n"
            "console script.\n"
            "\n"
            "If the GUI cannot start (for example on a headless system)\n"
            "the underlying error is printed and the command exits "
            "with a\n"
            "non-zero status. Set TN_VENV_GUI_NO_AUTOLOAD=1 to "
            "disable\n"
            "this subcommand entirely.\n"
            "\n"
            "Exit status: 0 on a clean window close, non-zero on "
            "startup failure.\n"
        ),
        package="tn-venv-gui",
    ),
}


_INSTALLED = False
_ORIGINAL_INNER_CLI_RUN = None  # type: ignore[var-annotated]


# --------------------------------------------------------------------- helpers


def list_subcommands() -> list[SubcommandSpec]:
    """Return every registered subcommand, sorted by name."""
    return [SUBCOMMANDS[name] for name in sorted(SUBCOMMANDS)]


def subcommand_help(name: str) -> str | None:
    """Return the long help text for a subcommand, or ``None`` if absent."""
    spec = SUBCOMMANDS.get(name)
    return spec.help if spec is not None else None


def _print_subcommand_help(name: str, stream=None) -> None:
    """Print the help for *name* to *stream* (defaults to stdout)."""
    out = stream or sys.stdout
    spec = SUBCOMMANDS.get(name)
    if spec is None:
        print(f"tn-venv: no such subcommand: {name!r}", file=out)
        print(
            f"available subcommands: {', '.join(sorted(SUBCOMMANDS))}",
            file=out,
        )
        return
    print(f"usage: tn-venv {spec.name} [-h]", file=out)
    print(file=out)
    # ``argparse.RawDescriptionHelpFormatter`` style — preserve line
    # breaks in the help text verbatim.
    print(spec.help, file=out)


def _run_original(args: Sequence[str] | None):
    """Delegate to the *real* (un-patched) inner ``cli_run``."""
    if _ORIGINAL_INNER_CLI_RUN is None:
        from tn_venv import cli_run as outer  # type: ignore[import-not-found]
        return outer(list(args) if args is not None else None)
    return _ORIGINAL_INNER_CLI_RUN(list(args) if args is not None else None)


def _about_version() -> str:
    try:
        from .version import __version__
    except Exception:
        return ""
    return f"v{__version__}"


def _launch_gui(args: Sequence[str]) -> int:
    """Translate ``tn-venv gui [...]`` into actual behaviour.

    Recognised flags:

    * ``-h`` / ``--help`` — print our subcommand help and exit 0.
    * (anything else) — silently ignored; the GUI itself doesn't take
      flags yet but we accept the arguments without erroring so future
      versions can grow options (e.g. ``tn-venv gui --dest .venv``).
    """
    # ``--help`` and ``-h`` short-circuit: show our own help rather
    # than starting the GUI.
    if any(a in {"-h", "--help"} for a in args):
        _print_subcommand_help("gui")
        return 0

    # Local import: launching the GUI pulls in tkinter. Keep that off
    # the import path of :mod:`tn_venv_gui` until the user actually
    # invokes the subcommand.
    from .app import launch

    # Tell the user (in their terminal) what's about to happen. This
    # is also useful when redirecting logs: the line is unambiguous.
    print(
        f"==> opening tn-venv-gui {_about_version()} (use "
        f"'tn-venv gui --help' for options; close the window to exit)"
    )
    try:
        launch()
    except Exception as exc:  # pragma: no cover - defensive
        print(f"tn-venv-gui failed to start: {exc!r}", file=sys.stderr)
        return 1
    return 0


def _handle_help_alias(args: Sequence[str]) -> int | None:
    """Return an exit code if ``args`` look like ``tn-venv help <sub>``.

    Returning ``None`` means "not a help request — fall through to the
    normal tn-venv CLI".
    """
    if not args or args[0] != "help":
        return None
    if len(args) == 1:
        # ``tn-venv help`` — let tn-venv's own ``--help`` handle it.
        return None
    _print_subcommand_help(args[1])
    return 0


# --------------------------------------------------------------------- patch


def install_subcommand() -> bool:
    """Patch :func:`tn_venv.cli.cli_run` to dispatch the GUI subcommand.

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

    Help-text integration is handled separately: tn-venv 1.x exposes
    the public :attr:`tn_venv.plugins.HookName.HELP_EPILOG` hook, and
    :class:`tn_venv_gui.plugin.GuiSubcommandPlugin` registers its own
    HELP_EPILOG listener — no ``build_parser`` monkey-patch is needed
    any more.
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
        _INSTALLED = True
        _ORIGINAL_INNER_CLI_RUN = original_inner
        return True

    _ORIGINAL_INNER_CLI_RUN = original_inner

    # -- wrap cli_run so the subcommand dispatches -------------------------
    def _patched(args=None, **kwargs):
        argv = list(args) if args is not None else sys.argv[1:]
        if not argv:
            return _ORIGINAL_INNER_CLI_RUN(args, **kwargs)  # type: ignore[misc]

        first = argv[0]

        # ``tn-venv help <subcommand>`` → show our subcommand help.
        if first == "help":
            rc = _handle_help_alias(argv)
            if rc is not None:
                return rc
            return _ORIGINAL_INNER_CLI_RUN(args, **kwargs)  # type: ignore[misc]

        # Registered subcommand (e.g. ``tn-venv gui ...``).
        spec = SUBCOMMANDS.get(first)
        if spec is not None:
            if spec.name == "gui":
                return _launch_gui(argv[1:])
            # Future-proof: dispatch table keyed by name. If we ever
            # add a second subcommand, register its handler here.
            return _ORIGINAL_INNER_CLI_RUN(args, **kwargs)  # type: ignore[misc]

        # Anything else (including ``-h``/``--help``) — original CLI.
        return _ORIGINAL_INNER_CLI_RUN(args, **kwargs)  # type: ignore[misc]

    _patched._tn_venv_gui_patched = True  # type: ignore[attr-defined]
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
