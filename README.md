# tn-venv-gui

![Official](https://img.shields.io/badge/official%20authorized-C0C0C0)

A graphical frontend for [tn-venv](https://github.com/tokenoodle-everything/tn-venv),
the batteries-included `virtualenv` alternative. Built with Tkinter so it runs anywhere
Python's standard library does — no extra GUI dependencies required.

![tn-venv-gui screenshot placeholder](screenshot/screenshot.png)

## Features

- Pick the destination folder and Python interpreter from a dropdown
  (auto-populated through `tn_venv.discovery.discover`).
- Toggle the most useful `tn-venv` flags without remembering the CLI:
  `--clear`, `--upgrade`, `--system-site-packages`, `--upgrade-pip`,
  `--offline`, `--symlinks` / `--copies`, custom prompt, and a list of
  preinstalled packages or requirements files.
- Real-time, color-coded log panel that streams `tn-venv`'s output as
  the environment is created.
- Background worker so the UI stays responsive while `pip install` runs.
- Saves your last-used settings to `~/.tn_venv_gui.json` so you can pick
  up where you left off.

## Installation

The GUI requires Python ≥ 3.9 and the `tn-venv` package (≥ 0.2.0).

```bash
# from a clone of this repository
pip install -e .

# or directly from PyPI
pip install tn-venv-gui
```

## Usage

After installation a `tn-venv-gui` console script is available:

```bash
tn-venv-gui
```

Or, without installing:

```bash
python -m tn_venv_gui
```

### As an optional subcommand of `tn-venv`

Because the package is also a [tn-venv plugin](https://github.com/tokenoodle-everything/tn-venv),
running `tn-venv-gui` once drops a `.pth` file in `site-packages/` that
auto-imports the package on every Python startup. From that point on,
`tn-venv` advertises and honours the `gui` subcommand:

```bash
tn-venv                       # create ./.venv as usual
tn-venv gui                   # open the GUI window
tn-venv gui --help            # detailed help for the subcommand
tn-venv help gui              # alias for the same help
tn-venv --list-pythons        # original tn-venv command, unchanged
tn-venv .venv --dry-run       # original dry-run output, unchanged
```

The `tn-venv --help` epilog automatically grows a section listing every
subcommand contributed by plugins:

```
optional subcommands provided by plugins:
  gui    launch the tn-venv-gui graphical frontend

Run 'tn-venv help <subcommand>' (or 'tn-venv <subcommand> --help') for details on a specific subcommand.
```

Knobs:

| Environment variable | Effect |
|----------------------|--------|
| `TN_VENV_GUI_NO_AUTOLOAD=1` | Don't monkey-patch `tn_venv.cli_run` even if imported. |
| `TN_VENV_GUI_NO_PTH=1` | Don't drop the auto-loading `.pth` file. |

The GUI plugin is also registered as a standard
`[project.entry-points."tn_venv.plugins"]` entry point, so once
tn-venv wires `load_plugins()` into its CLI (the loader is already
public API in tn-venv 1.0.0) the subcommand becomes discoverable
without any monkey-patching.

## Project layout

```
tn_venv_gui/
├── __init__.py        # exposes launch() and TnVenvGUI
├── __main__.py        # python -m tn_venv_gui entry point
├── app.py             # Tk root window, widgets, event wiring
├── workers.py         # background thread running tn_venv
├── python_list.py     # enumerates Python interpreters via tn_venv.discovery
└── version.py         # package version
```

## License

Tokenoodle-Everything License v1.0 (see `License.txt`). This is *not*
an OSI-approved open source license and forbids commercial use without
permission.

