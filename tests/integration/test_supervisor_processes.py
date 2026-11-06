"""launcher.supervisor managing real child processes."""

from __future__ import annotations

import subprocess
import sys

import pytest

from launcher.supervisor import Supervisor

from .conftest import is_running, posix_only, wait_for_file

pytestmark = pytest.mark.integration

SLEEP_FOREVER = "import time; time.sleep(600)"


def test_session_ends_with_the_first_essential_exit_and_stops_the_rest(spawn, python_exe):
    supervisor = Supervisor(poll_interval=0.02, grace_period=5)
    sleeper = supervisor.add(spawn([python_exe, "-c", SLEEP_FOREVER]))
    supervisor.add(spawn([python_exe, "-c", "import sys; sys.exit(3)"]))

    assert supervisor.wait() == 3
    assert not is_running(sleeper.pid)


def test_shutdown_stops_every_child(spawn, python_exe):
    supervisor = Supervisor(poll_interval=0.02, grace_period=5)
    children = [supervisor.add(spawn([python_exe, "-c", SLEEP_FOREVER])) for _ in range(3)]

    supervisor.shutdown()

    assert not any(is_running(p.pid) for p in children)


@posix_only
def test_shutdown_force_kills_a_child_that_ignores_sigterm(spawn, python_exe, tmp_path):
    ready = tmp_path / "ready"
    stubborn_code = (
        "import signal, time, pathlib;"
        "signal.signal(signal.SIGTERM, signal.SIG_IGN);"
        f"pathlib.Path({str(ready)!r}).write_text('1');"
        "time.sleep(600)"
    )
    supervisor = Supervisor(poll_interval=0.02, grace_period=0.3)
    stubborn = supervisor.add(spawn([python_exe, "-c", stubborn_code]))
    wait_for_file(ready)  # SIGTERM must arrive after the handler is installed

    supervisor.shutdown()

    assert stubborn.returncode == -9
    assert not is_running(stubborn.pid)


def test_non_essential_child_exiting_does_not_end_the_session(spawn, python_exe):
    supervisor = Supervisor(poll_interval=0.02, grace_period=5)
    supervisor.add(spawn([python_exe, "-c", "pass"]), essential=False)
    supervisor.add(spawn([python_exe, "-c", "import time, sys; time.sleep(0.4); sys.exit(4)"]))

    assert supervisor.wait() == 4


@pytest.mark.skipif(sys.platform == "win32", reason="POSIX signals")
def test_ctrl_c_stops_children_and_exits_zero(tmp_path, python_exe):
    """Run a supervisor in its own process, send it SIGINT, and check both it
    and its child are gone."""
    import os
    import signal

    from launcher.paths import REPO_ROOT

    pid_file = tmp_path / "child.pid"
    script = tmp_path / "session.py"
    script.write_text(
        "import subprocess, sys, pathlib\n"
        "from launcher.supervisor import Supervisor\n"
        "s = Supervisor(poll_interval=0.02)\n"
        "s.install_signal_handlers()\n"
        f"child = s.add(subprocess.Popen([sys.executable, '-c', {SLEEP_FOREVER!r}]))\n"
        f"pathlib.Path({str(pid_file)!r}).write_text(str(child.pid))\n"
        "sys.exit(s.wait())\n"
    )
    session = subprocess.Popen(
        [python_exe, str(script)],
        cwd=REPO_ROOT,
        env={**os.environ, "PYTHONPATH": str(REPO_ROOT)},
        stdout=subprocess.PIPE,
        text=True,
    )
    try:
        wait_for_file(pid_file)
        session.send_signal(signal.SIGINT)
        assert session.wait(timeout=10) == 0
        assert "Shutting down" in session.stdout.read()
        assert not is_running(int(pid_file.read_text()))
    finally:
        if session.poll() is None:
            session.kill()
