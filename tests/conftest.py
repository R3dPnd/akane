"""Shared fixtures for the persona repo's own tests (the `launcher` package).

The runtime submodule has its own suite under runtime/tests/ — these tests only
cover code that lives in this repo.
"""

from __future__ import annotations

import sys
from dataclasses import dataclass, field

import pytest


@dataclass
class FakeProcess:
    """Stand-in for `subprocess.Popen`: records terminate/kill calls and lets a
    test decide when (and with what code) the process "exits".

    Used by unit tests so the supervisor and commands can be exercised without
    spawning anything real.
    """

    name: str = "proc"
    returncode: int | None = None
    exit_on_terminate: bool = True
    terminated: bool = False
    killed: bool = False
    stdout: list[str] = field(default_factory=list)
    stderr: list[str] | None = None

    def poll(self) -> int | None:
        return self.returncode

    def wait(self, timeout: float | None = None) -> int:
        if self.returncode is None:
            import subprocess

            raise subprocess.TimeoutExpired(self.name, timeout)
        return self.returncode

    def terminate(self) -> None:
        self.terminated = True
        if self.exit_on_terminate and self.returncode is None:
            self.returncode = -15

    def kill(self) -> None:
        self.killed = True
        if self.returncode is None:
            self.returncode = -9


@pytest.fixture()
def fake_process_factory():
    """Build FakeProcess instances: `fake_process_factory(name="api")`."""
    return FakeProcess


@pytest.fixture()
def python_exe() -> str:
    """The interpreter running the tests — used to spawn real child processes."""
    return sys.executable
