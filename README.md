# tn-venv-gui

A graphical frontend for [tn-venv](https://github.com/tokenoodle-everything/tn-venv),
the batteries-included `virtualenv` alternative. Built with Tkinter so it runs anywhere
Python's standard library does — no extra GUI dependencies required.

<!-- ![tn-venv-gui screenshot placeholder](docs/screenshot.png) -->

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

