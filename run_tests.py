"""Run the full test suite for tn-venv-gui.

Three test scripts are exercised:

* ``subcommand_test.py`` — verifies the ``tn-venv gui`` subcommand
  integration without breaking the original tn-venv CLI.
* ``smoke_test.py`` — drives the GUI end-to-end and asserts a real
  venv is created with the preinstalled package.

Each script is invoked as a subprocess so its Tk resources are released
between the two runs.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path


def _run(cmd: list[str]) -> None:
    name = cmd[-1]
    print(f"\n==== {name} ====")
    result = subprocess.run(cmd, check=False)
    if result.returncode != 0:
        raise SystemExit(result.returncode)


def main() -> int:
    here = Path(__file__).parent
    py = sys.executable
    _run([py, str(here / "subcommand_test.py")])
    _run([py, str(here / "smoke_test.py")])
    print("\nALL TEST SUITES PASSED")
    return 0


if __name__ == "__main__":
    sys.exit(main())
