"""Own a set of child processes and shut them all down together.

A launcher session (e.g. `akane dev`) is a handful of children — API, Vite,
maybe an Electron window. The session ends when any *essential* child exits
(say the API crashes) or on Ctrl+C/SIGTERM; either way every other child is
stopped too, so nothing is left running in the background holding the port
or the microphone.
"""

from __future__ import annotations

import signal
import subprocess
import sys
import threading
import time
from typing import Protocol


class Process(Protocol):
    """The subset of `subprocess.Popen` the supervisor relies on."""

    returncode: int | None

    def poll(self) -> int | None: ...
    def wait(self, timeout: float | None = None) -> int: ...
    def terminate(self) -> None: ...
    def kill(self) -> None: ...


class Supervisor:
    """Tracks child processes for one launcher session.

    `poll_interval` is how often `wait()` checks for an exited child;
    `grace_period` is how long `shutdown()` gives each child to exit after
    SIGTERM before force-killing it.
    """

    def __init__(self, poll_interval: float = 0.2, grace_period: float = 5.0):
        self.poll_interval = poll_interval
        self.grace_period = grace_period
        self._essential: list[Process] = []
        self._all: list[Process] = []
        self._lock = threading.Lock()  # add() can be called from a background thread
        self._shutting_down = False

    def add(self, proc: Process, *, essential: bool = True) -> Process:
        """Track `proc`. An essential process exiting ends the session; a
        non-essential one (e.g. an Electron window the user closed) doesn't.

        A process added after shutdown has started is stopped immediately —
        otherwise one spawned by a background thread just as Ctrl+C lands
        would be orphaned.
        """
        with self._lock:
            late = self._shutting_down
            if not late:
                self._all.append(proc)
                if essential:
                    self._essential.append(proc)
        if late:
            self._stop(proc)
        return proc

    def wait(self) -> int:
        """Block until any essential process exits, then stop the rest.
        Returns the exit code of the process that ended the session (0 if
        there were no essential processes to wait on)."""
        exit_code = 0
        while self._essential:
            exited = next((p for p in self._essential if p.poll() is not None), None)
            if exited is not None:
                exit_code = exited.returncode or 0
                break
            time.sleep(self.poll_interval)
        self.shutdown()
        return exit_code

    def shutdown(self) -> None:
        """Stop every tracked process that's still running. Safe to call more than once."""
        with self._lock:
            self._shutting_down = True
            procs = list(self._all)
        for proc in procs:
            self._stop(proc)

    def install_signal_handlers(self) -> None:
        """On SIGINT (Ctrl+C) or SIGTERM, stop every child and exit with status 0."""

        def handle(signum, frame):
            print("\n[akane] Shutting down…", flush=True)
            self.shutdown()
            sys.exit(0)

        signal.signal(signal.SIGINT, handle)
        if hasattr(signal, "SIGTERM"):
            signal.signal(signal.SIGTERM, handle)

    def _stop(self, proc: Process) -> None:
        """SIGTERM, then SIGKILL if the process hasn't exited within the grace period."""
        if proc.poll() is not None:
            return
        try:
            proc.terminate()
            proc.wait(timeout=self.grace_period)
        except subprocess.TimeoutExpired:
            proc.kill()
            proc.wait()  # reap it, so it doesn't linger as a zombie
        except ProcessLookupError:
            pass  # exited between poll() and terminate()
