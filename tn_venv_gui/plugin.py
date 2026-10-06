"""
tn-venv :class:`Plugin` that exposes the GUI as an optional companion
to the command line.

Two complementary integration modes are supported:

1. **Lifecycle hooks** — register callbacks on the standard
   :class:`~tn_venv.plugins.HookName` points so the GUI can react to a
   ``run_session`` invocation in any embedding (including future
   versions of tn-venv that wire plugins into the session pipeline).
2. **Subcommand** — :func:`install_subcommand` from
   :mod:`tn_venv_gui.subcommand` adds a ``gui`` subcommand to
   :func:`tn_venv.cli_run`. The :class:`GuiSubcommandPlugin.register`
   call also installs the subcommand as a side effect, so any host
   that loads plugins through :func:`tn_venv.plugins.load_plugins`
   gets the subcommand for free.

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
    it installs the subcommand shim described in
    :mod:`tn_venv_gui.subcommand`. After that any tn-venv invocation
    starting with ``gui`` opens the GUI window instead of running the
    usual ``run_session`` pipeline.

    Set the environment variable ``TN_VENV_GUI_NO_AUTOLOAD=1`` to
    prevent the subcommand from being installed (useful for CI runs).
    """

    name = "tn-venv-gui"

    def register(self, hooks: Any) -> None:  # noqa: D401 - Plugin API
        if os.environ.get("TN_VENV_GUI_NO_AUTOLOAD"):
            return
        subcommand.install_subcommand()


# --------------------------------------------------------------------- hooks


class GuiHookPlugin(Plugin):
    """Plugin that reacts to ``run_session`` lifecycle hooks.

    When tn-venv (now or in the future) wires plugins into the session
    pipeline, this plugin will:

    * log a line at ``session_start`` so users can see the GUI plugin
      was loaded;
    * capture the final :class:`~tn_venv.session.SessionResult` at
      ``session_end`` and stash it under :attr:`HookContext.data` so
      other plugins or the host application can read it.

    In tn-venv 1.0.0 the hook emitter is not yet wired into
    :func:`run_session`, so these callbacks never fire today — but
    declaring them is the right shape for the next release and lets
    us validate the plugin contract without touching tn-venv itself.
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
