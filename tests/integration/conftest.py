"""Helpers for integration tests: real child processes, real sockets.

Safety rule for this suite: nothing here may find or stop a *real* running
Akane. Ports are ephemeral (never 8000/3000), and process discovery is always
narrowed to processes the test itself spawned.
"""

from __future__ import annotations

import socket
import stat
import subprocess
import sys
import textwrap
import time
from pathlib import Path

import psutil
import pytest

posix_only = pytest.mark.skipif(sys.platform == "win32", reason="uses executable shebang scripts / POSIX signals")


@pytest.fixture()
def free_port():
    """Return a function that finds an unused localhost TCP port."""

    def find() -> int:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
            sock.bind(("127.0.0.1", 0))
            return sock.getsockname()[1]

    return find


@pytest.fixture()
def make_script(tmp_path):
    """Write an executable Python script (run by the test interpreter) and return its path."""

    def make(name: str, body: str) -> Path:
        path = tmp_path / name
        path.write_text(f"#!{sys.executable}\n" + textwrap.dedent(body))
        path.chmod(path.stat().st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)
        return path

    return make


@pytest.fixture()
def spawn():
    """Spawn real child processes, and make sure every one is gone after the test."""
    children: list[subprocess.Popen] = []

    def start(cmd: list[str], **kwargs) -> subprocess.Popen:
        proc = subprocess.Popen(cmd, **kwargs)
        children.append(proc)
        return proc

    yield start

    for proc in children:
        if proc.poll() is None:
            proc.kill()
            proc.wait(timeout=5)


def wait_for_file(path: Path, timeout: float = 10.0) -> None:
    """Block until `path` exists and is non-empty (child processes write
    marker files once they've finished starting up)."""
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if path.exists() and path.stat().st_size > 0:
            return
        time.sleep(0.02)
    raise AssertionError(f"{path} was never written")


def is_running(pid: int) -> bool:
    try:
        return psutil.Process(pid).status() != psutil.STATUS_ZOMBIE
    except psutil.NoSuchProcess:
        return False
