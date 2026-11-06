"""Run the launcher under the repo's own .venv.

`akane` is installed as a symlink (~/.local/bin/akane → akane.py), so its
`#!/usr/bin/env python3` picks up whatever python3 is first on PATH — often a
different project's venv without psutil or PyYAML. akane.py calls ensure_venv
before importing anything else, which re-executes it under .venv/bin/python.

Stdlib-only on purpose: it runs before the venv's packages are available.
"""

from __future__ import annotations

import os
import sys
from collections.abc import Callable
from pathlib import Path

VENV_DIR = Path(__file__).resolve().parent.parent / ".venv"


def ensure_venv(
    argv: list[str],
    *,
    script: Path,
    prefix: str = sys.prefix,
    venv_dir: Path = VENV_DIR,
    execv: Callable[[str, list[str]], object] = os.execv,
) -> None:
    """Replace this process with `<venv>/bin/python <script> <argv...>`, unless
    it's already running in that venv or the venv doesn't exist yet."""
    python = venv_dir / "bin" / "python"
    if Path(prefix).resolve() == venv_dir.resolve() or not python.exists():
        return
    # The venv's python, not its resolved target: a venv is selected by the
    # path it was invoked through (pyvenv.cfg next to it).
    execv(str(python), [str(python), str(script), *argv])
