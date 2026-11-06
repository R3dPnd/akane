"""Building and spawning Akane's child processes: the runtime API (uvicorn),
the UI (an `npm run` script in runtime/ui), and a standalone Electron window.

Spawning is kept separate from supervising (see supervisor.py) so each can be
tested on its own.
"""

from __future__ import annotations

import os
import subprocess
import sys
import threading
from collections.abc import Iterable, Mapping
from typing import TextIO

from launcher import paths

# ANSI-coloured prefixes so interleaved API/UI output stays readable.
API_PREFIX = "\033[36m[api]\033[0m "
UI_PREFIX = "\033[35m[ui] \033[0m "

# Line-buffered text pipes, so output can be forwarded line by line as it arrives.
_CAPTURED = {"stdout": subprocess.PIPE, "text": True, "bufsize": 1}


def persona_env() -> dict[str, str]:
    """The PND_* variables that tell Vite, Electron and the API which ports and
    name this persona uses (they don't read config.yaml themselves)."""
    return {
        "PND_API_PORT": str(paths.API_PORT),
        "PND_UI_PORT": str(paths.UI_PORT),
        "PND_PERSONA_NAME": paths.PERSONA_NAME,
    }


def build_api_env(voice: bool, base_env: Mapping[str, str] | None = None, speak: bool = False) -> dict[str, str]:
    """Environment for the API process.

    - PND_CONFIG_PATH points the runtime at this repo's config.yaml (it would
      otherwise look inside runtime/).
    - NO_VOICE=1 unless `voice` — and cleared when `voice` is requested, so a
      stray `NO_VOICE` exported in the shell can't silently override `--voice`.
    """
    env = dict(os.environ if base_env is None else base_env)
    env["PYTHONUNBUFFERED"] = "1"
    env["PND_CONFIG_PATH"] = str(paths.CONFIG_PATH)
    env.update(persona_env())
    env.pop("PND_VOICE_MODE", None)
    if voice or speak:
        env.pop("NO_VOICE", None)
    else:
        env["NO_VOICE"] = "1"
    if speak and not voice:
        env["PND_VOICE_MODE"] = "speak"  # voice pipeline without the mic
    return env


def spawn_api(voice: bool, capture_output: bool = True, speak: bool = False) -> subprocess.Popen:
    """Start the runtime's FastAPI app under uvicorn, from inside runtime/.

    With `capture_output`, stdout/stderr are piped so the caller can prefix and
    forward them (see forward_output); otherwise the API writes straight to
    this terminal.
    """
    command = [
        str(paths.VENV_UVICORN),
        "app.main:app",
        "--host", "0.0.0.0",
        "--port", str(paths.API_PORT),
    ]
    output = {**_CAPTURED, "stderr": subprocess.PIPE} if capture_output else {}
    return subprocess.Popen(command, cwd=str(paths.RUNTIME_DIR), env=build_api_env(voice, speak=speak), **output)


def spawn_npm_script(script: str) -> subprocess.Popen:
    """Run `npm run <script>` in runtime/ui (e.g. `dev` for Vite, `electron:dev`
    for Vite + Electron), with stderr merged into the captured stdout."""
    return subprocess.Popen(
        [paths.node_tool("npm"), "run", script],
        cwd=str(paths.UI_DIR),
        env={**os.environ, **persona_env()},
        stderr=subprocess.STDOUT,
        **_CAPTURED,
    )


def spawn_electron_window() -> subprocess.Popen:
    """Open a fullscreen Electron window onto the already-running Vite server.

    Electron's dev-mode code path (runtime/ui/electron/main.cjs) just points at
    the Vite dev server, so this launches Electron directly rather than via the
    `electron:dev` npm script — which would start a second, redundant Vite.
    """
    env = {**os.environ, **persona_env(), "NODE_ENV": "development", "PND_FULLSCREEN": "1"}
    return subprocess.Popen([paths.node_tool("npx"), "electron", "."], cwd=str(paths.UI_DIR), env=env)


def stream_lines(stream: Iterable[str], prefix: str, out: TextIO | None = None) -> None:
    """Copy each line of `stream` to `out` (default: stdout) with `prefix`.
    Returns quietly when the pipe is closed underneath it at shutdown."""
    out = out or sys.stdout
    try:
        for line in stream:
            print(f"{prefix} {line}", end="", file=out, flush=True)
    except ValueError:  # "I/O operation on closed file"
        pass


def forward_output(proc: subprocess.Popen, prefix: str, out: TextIO | None = None) -> list[threading.Thread]:
    """Forward whichever of `proc`'s stdout/stderr were captured, each on its
    own daemon thread. Returns the started threads."""
    threads = []
    for stream in (proc.stdout, proc.stderr):
        if stream is None:
            continue
        thread = threading.Thread(target=stream_lines, args=(stream, prefix, out), daemon=True)
        thread.start()
        threads.append(thread)
    return threads
