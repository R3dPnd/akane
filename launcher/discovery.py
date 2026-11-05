"""Find akane processes already running on this machine — for `akane stop` and
`akane restart`.

That means the `akane.py` launcher itself, plus its API (uvicorn), Vite, and
Electron children — including orphans whose launcher is gone (terminal closed,
or an earlier kill only got part of the process tree), which is how multiple
overlapping instances used to end up fighting over the microphone.

The matching rules are pure functions over a command line and working
directory, so they can be tested without real processes.
"""

from __future__ import annotations

from collections.abc import Iterable
from pathlib import PurePath

import psutil

from launcher.paths import RUNTIME_DIR, UI_DIR

# The launcher's script name as it appears in a command line: `akane.py`
# itself, or the `akane` symlink it's usually installed as (~/.local/bin/akane).
LAUNCHER_SCRIPT_NAMES = {"akane.py", "akane"}

# Launcher subcommands that ARE a running Akane (API/UI/voice). Everything else
# (stop, restart, hunt, schedule, jobs-app) is a one-shot action: `akane stop`
# leaves it alone — the nightly launchd hunt must survive a stop — and
# `akane restart` never relaunches it.
_RUNNING_COMMANDS = {"dev", "code", "electron", "start"}

_GONE = (psutil.NoSuchProcess, psutil.AccessDenied, psutil.ZombieProcess)


def launcher_args(cmdline: list[str]) -> list[str] | None:
    """If `cmdline` is a Python interpreter running akane.py (or its `akane`
    symlink), return the arguments after the script (e.g. `["dev", "--voice"]`);
    otherwise None.

    Requiring a Python interpreter is what keeps an editor or pager that has
    akane.py open (`vim akane.py`) from being mistaken for the launcher.
    """
    if not cmdline or not PurePath(cmdline[0]).name.lower().startswith("python"):
        return None
    for i, arg in enumerate(cmdline[1:], start=1):
        if PurePath(arg).name in LAUNCHER_SCRIPT_NAMES:
            return cmdline[i + 1:]
        if not arg.startswith("-"):
            return None  # the interpreter is running some other script
    return None


def is_akane_process(cmdline: list[str], cwd: str | None) -> bool:
    """Whether a process with this command line and working directory is part
    of a running Akane: the launcher running dev/electron/start (any cwd), or
    uvicorn/Vite/Electron from inside this repo's runtime/ submodule."""
    args = launcher_args(cmdline)
    if args:
        return args[0] in _RUNNING_COMMANDS
    joined = " ".join(cmdline).lower()
    if cwd == str(RUNTIME_DIR) and "app.main:app" in joined:
        return True
    if cwd == str(UI_DIR) and ("vite" in joined or "electron" in joined):
        return True
    return False


def list_processes() -> Iterable[psutil.Process]:
    """Every process on the machine (a seam for tests to narrow down)."""
    return psutil.process_iter(["pid"])


def find_akane_processes(processes: Iterable[psutil.Process], exclude_pid: int) -> list[psutil.Process]:
    """The akane processes among `processes`, skipping `exclude_pid` (the
    caller itself) and any process that vanishes or denies access mid-scan."""
    found = []
    for proc in processes:
        if proc.pid == exclude_pid:
            continue
        try:
            cmdline = proc.cmdline()
        except _GONE:
            continue
        try:
            cwd = proc.cwd()
        except _GONE:
            cwd = None  # can still match as the launcher, which doesn't need a cwd
        if is_akane_process(cmdline, cwd):
            found.append(proc)
    return found


def find_restartable_launcher_args(processes: Iterable[psutil.Process], exclude_pid: int) -> list[str] | None:
    """The arguments of a running launcher worth relaunching (`dev`,
    `electron --voice`, ...) — not a concurrent `stop`/`restart`, and not
    `exclude_pid` (the caller). None if there isn't one."""
    for proc in processes:
        if proc.pid == exclude_pid:
            continue
        try:
            args = launcher_args(proc.cmdline())
        except _GONE:
            continue
        if args and args[0] in _RUNNING_COMMANDS:
            return args
    return None


def stop_processes(procs: list[psutil.Process], timeout: float = 5.0) -> list[psutil.Process]:
    """Terminate `procs`, wait up to `timeout` seconds, then force-kill any
    still alive. Returns the ones that had to be force-killed."""
    for proc in procs:
        try:
            proc.terminate()
        except psutil.NoSuchProcess:
            pass
    _, alive = psutil.wait_procs(procs, timeout=timeout)
    for proc in alive:
        try:
            proc.kill()
        except psutil.NoSuchProcess:
            pass
    return alive
