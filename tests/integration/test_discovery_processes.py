"""launcher.discovery and `akane stop`/`akane restart` against real processes.

Every test narrows `discovery.list_processes` to processes the test spawned,
so a real running Akane on this machine is never found or stopped.
"""

from __future__ import annotations

import os

import psutil
import pytest

from launcher import commands, discovery
from launcher.paths import RUNTIME_DIR

from .conftest import is_running, posix_only, wait_for_file

pytestmark = pytest.mark.integration


@pytest.fixture()
def fake_launcher(tmp_path, spawn, python_exe):
    """Start `python <tmp>/akane.py <args...>` — a stand-in launcher that just sleeps."""
    script = tmp_path / "akane.py"
    script.write_text("import time\ntime.sleep(600)\n")

    def start(*args: str):
        return spawn([python_exe, str(script), *args])

    return start


@pytest.fixture()
def only(monkeypatch):
    """Restrict process discovery to the given Popen objects."""

    def restrict(*popens):
        monkeypatch.setattr(discovery, "list_processes", lambda: [psutil.Process(p.pid) for p in popens])

    return restrict


def test_list_processes_sees_this_test_process():
    assert os.getpid() in {p.pid for p in discovery.list_processes()}


def test_finds_a_real_launcher_process(fake_launcher):
    launcher = fake_launcher("dev", "--voice")
    found = discovery.find_akane_processes([psutil.Process(launcher.pid)], exclude_pid=os.getpid())
    assert [p.pid for p in found] == [launcher.pid]


def test_finds_an_api_process_running_from_the_runtime_dir(spawn, python_exe):
    # Stands in for `uvicorn app.main:app` launched with cwd=runtime/.
    api = spawn([python_exe, "-c", "import time; time.sleep(600)", "app.main:app"], cwd=RUNTIME_DIR)
    found = discovery.find_akane_processes([psutil.Process(api.pid)], exclude_pid=os.getpid())
    assert [p.pid for p in found] == [api.pid]


def test_ignores_an_unrelated_process(spawn, python_exe):
    other = spawn([python_exe, "-c", "import time; time.sleep(600)"])
    assert discovery.find_akane_processes([psutil.Process(other.pid)], exclude_pid=os.getpid()) == []


def test_cmd_stop_stops_akane_processes_and_leaves_others_alone(fake_launcher, spawn, python_exe, only, capsys):
    launcher = fake_launcher("dev")
    bystander = spawn([python_exe, "-c", "import time; time.sleep(600)"])
    only(launcher, bystander)

    assert commands.cmd_stop() == 0

    launcher.wait(timeout=10)
    assert not is_running(launcher.pid)
    assert is_running(bystander.pid)
    assert f"Stopping 1 process(es): [{launcher.pid}]" in capsys.readouterr().out


@posix_only
def test_stop_processes_force_kills_a_process_that_ignores_sigterm(tmp_path, spawn, python_exe):
    ready = tmp_path / "ready"
    stubborn = spawn([
        python_exe, "-c",
        "import signal, time, pathlib;"
        "signal.signal(signal.SIGTERM, signal.SIG_IGN);"
        f"pathlib.Path({str(ready)!r}).write_text('1');"
        "time.sleep(600)",
    ])
    wait_for_file(ready)

    force_killed = discovery.stop_processes([psutil.Process(stubborn.pid)], timeout=0.3)

    assert [p.pid for p in force_killed] == [stubborn.pid]
    stubborn.wait(timeout=10)


def test_cmd_restart_stops_the_launcher_and_relaunches_with_its_args(fake_launcher, only, monkeypatch):
    launcher = fake_launcher("electron", "--voice")
    only(launcher)
    monkeypatch.setattr(commands.time, "sleep", lambda _s: None)
    relaunched = []

    exit_code = commands.cmd_restart(relaunch=lambda args: relaunched.append(args) or 0)

    assert exit_code == 0
    assert relaunched == [["electron", "--voice"]]
    launcher.wait(timeout=10)
    assert not is_running(launcher.pid)


def test_cmd_restart_ignores_a_concurrent_stop(fake_launcher, only):
    only(fake_launcher("stop"))
    assert commands.cmd_restart(relaunch=lambda args: pytest.fail("should not relaunch")) == 1
