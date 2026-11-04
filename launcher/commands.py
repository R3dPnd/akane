"""One function per `akane` subcommand. Each returns a process exit code.

Modules are referenced as `processes.spawn_api(...)`, `paths.API_PORT`, etc.
(rather than importing names directly) so tests can substitute them.
"""

from __future__ import annotations

import os
import threading
import time
import webbrowser
from collections.abc import Callable

from launcher import discovery, paths, preflight, processes, readiness
from launcher.supervisor import Supervisor

API_STARTUP_TIMEOUT = 30.0
UI_STARTUP_TIMEOUT = 30.0

_INFO = "\033[36m[akane]\033[0m"
_OK = "\033[32m[akane]\033[0m"
_ERROR = "\033[31m[akane]\033[0m"


def run_in_background(fn: Callable[..., object], *args: object) -> None:
    """Run `fn(*args)` on a daemon thread, so it never blocks shutdown."""
    threading.Thread(target=fn, args=args, daemon=True).start()


def _start_api_and_wait(supervisor: Supervisor, voice: bool, speak: bool = False) -> bool:
    """Spawn the API with its output forwarded, and block until its health
    endpoint answers. On failure, report it and stop the API; returns whether
    it came up."""
    api = supervisor.add(processes.spawn_api(voice, speak=speak))
    processes.forward_output(api, processes.API_PREFIX)

    print(f"{_INFO} Waiting for API on :{paths.API_PORT}…", flush=True)
    ready = readiness.wait_until_serving(
        paths.api_health_url(paths.API_PORT),
        timeout=API_STARTUP_TIMEOUT,
        should_abort=lambda: api.poll() is not None,  # crashed: don't sit out the timeout
    )
    if not ready:
        print(f"{_ERROR} API did not come up within {API_STARTUP_TIMEOUT:.0f}s — aborting.", flush=True)
        supervisor.shutdown()
    return ready


def _open_when_ui_ready(supervisor: Supervisor, in_electron: bool) -> None:
    """Once Vite is serving, open the UI — in a fullscreen Electron window if
    `in_electron`, otherwise a browser tab. Without this, `akane dev` starts
    everything with nothing visibly appearing on screen."""
    url = paths.ui_url(paths.UI_PORT)
    if not readiness.wait_until_serving(url, timeout=UI_STARTUP_TIMEOUT):
        return
    if in_electron:
        # Closing the window shouldn't take the API down with it, but the
        # window should still close when the session ends.
        supervisor.add(processes.spawn_electron_window(), essential=False)
    else:
        webbrowser.open(url)


def _voice_label(voice: bool, speak: bool) -> str:
    if voice:
        return "with voice"
    return "speak-only: replies read aloud, mic off" if speak else "NO_VOICE=1"


def cmd_dev(voice: bool = False, speak: bool = False) -> int:
    """API + Vite dev server. Opens a browser tab — or, with `voice`, a
    fullscreen Electron window, since running Akane for real should feel like
    an app rather than a dev-server tab."""
    if not preflight.run(voice, ui=True, speak=speak, electron=voice):
        return 1
    supervisor = Supervisor()
    supervisor.install_signal_handlers()
    if not _start_api_and_wait(supervisor, voice, speak):
        return 1

    ui = supervisor.add(processes.spawn_npm_script("dev"))
    processes.forward_output(ui, processes.UI_PREFIX)
    run_in_background(_open_when_ui_ready, supervisor, voice)

    voice_label = _voice_label(voice, speak)
    window_label = "  (fullscreen Electron window)" if voice else ""
    print(f"{_OK} API  → http://localhost:{paths.API_PORT}  ({voice_label})", flush=True)
    print(f"{_OK} UI   → {paths.ui_url(paths.UI_PORT)}{window_label}", flush=True)
    print(f"{_OK} Ctrl+C to stop both\n", flush=True)
    return supervisor.wait()


def cmd_electron(voice: bool = False, speak: bool = False) -> int:
    """API + the UI's `electron:dev` script (Vite with hot reload, inside Electron)."""
    if not preflight.run(voice, ui=True, speak=speak, electron=True):
        return 1
    supervisor = Supervisor()
    supervisor.install_signal_handlers()
    if not _start_api_and_wait(supervisor, voice, speak):
        return 1

    electron = supervisor.add(processes.spawn_npm_script("electron:dev"))
    processes.forward_output(electron, processes.UI_PREFIX)

    voice_label = _voice_label(voice, speak)
    print(f"{_OK} API      → http://localhost:{paths.API_PORT}  ({voice_label})", flush=True)
    print(f"{_OK} Electron → opening window…", flush=True)
    print(f"{_OK} Ctrl+C to stop all\n", flush=True)
    return supervisor.wait()


def cmd_start() -> int:
    """API only, voice enabled, writing straight to this terminal."""
    if not preflight.run(True, ui=False):
        return 1
    supervisor = Supervisor()
    supervisor.install_signal_handlers()
    supervisor.add(processes.spawn_api(voice=True, capture_output=False))
    return supervisor.wait()


def cmd_stop() -> int:
    """Stop every akane process on this machine — launcher, API, Vite,
    Electron — including orphans left behind by a closed terminal."""
    targets = discovery.find_akane_processes(discovery.list_processes(), exclude_pid=os.getpid())
    if not targets:
        print("[akane] Nothing running.")
        return 0

    print(f"[akane] Stopping {len(targets)} process(es): {[p.pid for p in targets]}")
    force_killed = discovery.stop_processes(targets)
    if force_killed:
        print(
            f"[akane] Force-killed {len(force_killed)} process(es) that didn't exit cleanly: "
            f"{[p.pid for p in force_killed]}"
        )
    print("[akane] Stopped.")
    return 0


def cmd_restart(relaunch: Callable[[list[str]], int]) -> int:
    """Stop the running launcher and start it again with the same subcommand
    and flags, read from its live command line — so you don't have to retype
    them. `relaunch` runs the recovered arguments (the CLI passes its own
    `main`).

    This is the manual, human-triggered restart (the dashboard button and the
    "restart Akane" voice command reach the same outcome via the runtime);
    Akane never restarts himself after editing his own code.
    """
    args = discovery.find_restartable_launcher_args(discovery.list_processes(), exclude_pid=os.getpid())
    if not args:
        print("[akane] Nothing running to restart — use `akane dev`/`akane electron`/`akane start` instead.")
        return 1

    print(f"[akane] Restarting with args: {args}")
    cmd_stop()
    time.sleep(1)  # let the OS release the API/UI ports before rebinding them
    return relaunch(args)
