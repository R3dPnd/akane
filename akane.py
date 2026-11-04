#!/usr/bin/env python3
"""akane CLI — developer tooling for Akane.

Usage:
    akane dev [--voice]       API + UI dev servers; browser tab (or, with --voice,
                              the voice pipeline and a fullscreen Electron window)
    akane code                Alias for `dev`
    akane electron [--voice]  API + Electron dev window
    akane start               API only, with the voice pipeline enabled
    akane stop                Stop every running akane process, including orphans
    akane restart             Stop and relaunch with the same mode/flags

Run `python akane.py --help` for details. The implementation lives in the
`launcher` package; this file stays as the entry point because `akane stop` and
`akane restart` find the running launcher by looking for `akane.py` in process
command lines.
"""

import sys
from pathlib import Path

# Make the launcher importable however this file is invoked (directly, or via
# the ~/.local/bin/akane symlink).
REPO_ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(REPO_ROOT))

from launcher.venv import ensure_venv  # noqa: E402  (stdlib only)

if __name__ == "__main__":
    ensure_venv(sys.argv[1:], script=REPO_ROOT / "akane.py")

    from launcher.cli import main

    sys.exit(main(sys.argv[1:]))
