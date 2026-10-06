"""
tn-venv :class:`Plugin` that exposes the GUI as an optional companion
to the command line.

Three complementary integration modes are supported:

1. **Lifecycle hooks** — register callbacks on the standard
   :class:`~tn_venv.plugins.HookName` points so the GUI can react to a
   ``run_session`` invocation.
2. **Subcommand** — :func:`install_subcommand` from
   :mod:`tn_venv_gui.subcommand` adds a ``gui`` subcommand to
   :func:`tn_venv.cli_run`. The :class:`GuiSubcommandPlugin.register`
   call also installs the subcommand as a side effect, so any host
   that loads plugins through :func:`tn_venv.plugins.load_plugins`
   gets the subcommand for free.
3. **Help epilog** — :class:`GuiSubcommandPlugin` registers a
   :attr:`~tn_venv.plugins.HookName.HELP_EPILOG` listener that
   appends the standard "optional subcommands provided by plugins"
   block to ``tn-venv --help`` output. tn-venv 1.x calls this hook
   lazily on ``--help``; older tn-venv builds (which lack
   ``HELP_EPILOG``) skip it without error.

The plugin is intentionally tolerant of older or future tn-venv builds:
if any required symbol is missing, the plugin is still constructable —
it just degrades to a no-op.
"""

from __future__ import annotations

import os
from typing import Any

from tn_venv.plugins import Plugin

from . import subcommand

__all__ = ["GuiSubcommandPlugin", "GuiHookPlugin"]


# --------------------------------------------------------------------- subcommand


class GuiSubcommandPlugin(Plugin):
    """Plugin that wires ``tn-venv gui [...]`` into the tn-venv CLI.

    When :meth:`register` is called by :func:`tn_venv.plugins.load_plugins`
    it:

    * installs the subcommand shim described in
      :mod:`tn_venv_gui.subcommand` so ``tn-venv gui [...]`` opens the
      GUI window, and
    * registers a :attr:`~tn_venv.plugins.HookName.HELP_EPILOG`
      listener that contributes the "optional subcommands provided by
      plugins" block to ``tn-venv --help``.

    The HELP_EPILOG block is the modern, public replacement for the
    older monkey-patch of :func:`tn_venv.cli.build_parser` that
    earlier versions of this package used. tn-venv 1.x surfaces
    HELP_EPILOG natively; the listener is a no-op on older builds.

    Set the environment variable ``TN_VENV_GUI_NO_AUTOLOAD=1`` to
    prevent both the subcommand and the help epilog from being
    installed (useful for CI runs).
    """

    name = "tn-venv-gui"

    def register(self, hooks: Any) -> None:  # noqa: D401 - Plugin API
        if os.environ.get("TN_VENV_GUI_NO_AUTOLOAD"):
            return
        subcommand.install_subcommand()
        # Public HELP_EPILOG hook — tn-venv >= 1.x renders this text
        # at the end of ``tn-venv --help``. Older builds don't have
        # the enum member; the AttributeError is silently swallowed.
        try:
            from tn_venv.plugins import HookName  # noqa: F401

            hooks.add(
                HookName.HELP_EPILOG,
                _gui_help_epilog,
                plugin_name=self.name,
            )
        except (ImportError, AttributeError):
            # tn-venv older than 1.x: no HELP_EPILOG hook.
            pass


def _gui_help_epilog() -> str | None:
    """Return the text appended to ``tn-venv --help`` by the GUI plugin.

    Returns ``None`` when the subcommand table is empty so tn-venv
    can omit the block entirely.
    """
    specs = subcommand.list_subcommands()
    if not specs:
        return None
    lines = ["", "optional subcommands provided by plugins:"]
    width = max(len(spec.name) for spec in specs)
    for spec in specs:
        lines.append(f"  {spec.name.ljust(width)}    {spec.short}")
    lines.append("")
    lines.append(
        "Run 'tn-venv help <subcommand>' (or 'tn-venv <subcommand> "
        "--help') for details on a specific subcommand."
    )
    return "\n".join(lines)


# --------------------------------------------------------------------- hooks


class GuiHookPlugin(Plugin):
    """Plugin that reacts to ``run_session`` lifecycle hooks.

    * log a line at ``session_start`` so users can see the GUI plugin
      was loaded;
    * capture the final :class:`~tn_venv.session.SessionResult` at
      ``session_end`` and stash it under :attr:`HookContext.data` so
      other plugins or the host application can read it.

    Declaring these hooks is forward-compatible: older tn-venv builds
    that don't wire plugins into ``run_session`` simply never fire
    the callbacks, but the plugin still loads cleanly.
    """

    name = "tn-venv-gui-hooks"
    #: Run after the built-in ``VersionStampPlugin`` so its data
    #: values are already in place when we read them.
    _PRIORITY = 50

    def register(self, hooks: Any) -> None:  # noqa: D401 - Plugin API
        try:
            from tn_venv.plugins import HookName
        except Exception:
            # Older tn-venv without the plugin API: silently no-op.
            return

        hooks.add(
            HookName.SESSION_START,
            self._on_session_start,
            priority=self._PRIORITY,
            plugin_name=self.name,
        )
        hooks.add(
            HookName.SESSION_END,
            self._on_session_end,
            priority=self._PRIORITY,
            plugin_name=self.name,
        )

    # -- hook bodies ---------------------------------------------------------

    @staticmethod
    def _on_session_start(ctx: Any) -> None:
        # ``ctx.options`` is the resolved Options object. We stash a
        # marker so tests can assert the hook fired.
        reporter = ctx.reporter
        if reporter is not None:
            reporter.info("[tn-venv-gui] plugin loaded — observing session")
        if ctx.data is not None:
            ctx.data.setdefault("gui_plugin_observed", []).append("session_start")

    @staticmethod
    def _on_session_end(ctx: Any) -> None:
        # ``ctx.result`` is the SessionResult built by run_session. We
        # expose its ``env_dir`` so a host application (or a follow-up
        # plugin) can read it without re-running the pipeline.
        result = getattr(ctx, "result", None)
        env_dir = getattr(result, "env_dir", None)
        reporter = ctx.reporter
        if reporter is not None:
            where = f" → {env_dir}" if env_dir is not None else ""
            reporter.info(f"[tn-venv-gui] session finished{where}")
        if ctx.data is not None:
            ctx.data.setdefault("gui_plugin_observed", []).append("session_end")
            if env_dir is not None:
                ctx.data["last_env_dir"] = env_dir


# Convenience alias — the ``PLUGIN_ENTRY_POINT`` value advertised in
# :file:`pyproject.toml` may point at any object. Most projects point at
# a single :class:`Plugin` subclass, so we expose one canonical symbol.
PLUGIN = GuiSubcommandPlugin
