"""Unit tests for launcher.discovery — recognising akane processes from their
command line and working directory, without touching real processes."""

from __future__ import annotations

from dataclasses import dataclass

import psutil
import pytest

from launcher import discovery
from launcher.paths import RUNTIME_DIR, UI_DIR

PY = "/Users/me/akane/.venv/bin/python"


class TestLauncherArgs:
    def test_returns_args_after_akane_py(self):
        assert discovery.launcher_args([PY, "akane.py", "dev", "--voice"]) == ["dev", "--voice"]

    def test_matches_absolute_script_path(self):
        assert discovery.launcher_args([PY, "/repo/akane.py", "start"]) == ["start"]

    def test_matches_interpreter_flags_before_script(self):
        assert discovery.launcher_args(["python3", "-u", "akane.py", "dev"]) == ["dev"]

    def test_matches_macos_framework_python(self):
        exe = "/Library/Frameworks/Python.framework/Versions/3.12/Resources/Python.app/Contents/MacOS/Python"
        assert discovery.launcher_args([exe, "akane.py", "electron"]) == ["electron"]

    def test_matches_the_installed_akane_symlink(self):
        # `akane` is typically installed as ~/.local/bin/akane -> akane.py, so its
        # command line names the symlink rather than akane.py.
        assert discovery.launcher_args(["python3", "/Users/me/.local/bin/akane", "dev"]) == ["dev"]

    def test_bare_invocation_has_empty_args(self):
        assert discovery.launcher_args([PY, "akane.py"]) == []

    @pytest.mark.parametrize(
        "cmdline",
        [
            ["vim", "akane.py"],
            ["code", "/repo/akane.py"],
            ["grep", "-n", "cmd_stop", "akane.py"],
            ["less", "notakane.py"],
            [PY, "other.py", "akane.py"],
            [PY, "-u"],  # interpreter with only flags, e.g. a REPL
            [],
        ],
    )
    def test_ignores_non_launcher_processes(self, cmdline):
        # Regression: `akane stop` used to substring-match "akane.py" anywhere in
        # the command line, so it would kill an editor that had the file open.
        assert discovery.launcher_args(cmdline) is None


class TestIsAkaneProcess:
    def test_launcher_matches_regardless_of_cwd(self):
        assert discovery.is_akane_process([PY, "akane.py", "dev"], cwd="/anywhere")

    def test_uvicorn_in_runtime_dir_matches(self):
        cmdline = ["/repo/.venv/bin/uvicorn", "app.main:app", "--port", "8000"]
        assert discovery.is_akane_process(cmdline, cwd=str(RUNTIME_DIR))

    def test_uvicorn_elsewhere_does_not_match(self):
        cmdline = ["uvicorn", "app.main:app"]
        assert not discovery.is_akane_process(cmdline, cwd="/some/other/project")

    @pytest.mark.parametrize("tool", ["node /x/node_modules/.bin/vite", "node_modules/electron/dist/Electron ."])
    def test_ui_tools_in_ui_dir_match(self, tool):
        assert discovery.is_akane_process(tool.split(), cwd=str(UI_DIR))

    def test_ui_tools_elsewhere_do_not_match(self):
        assert not discovery.is_akane_process(["node", "vite"], cwd="/other/ui")

    def test_unrelated_process_does_not_match(self):
        assert not discovery.is_akane_process(["/bin/zsh"], cwd=str(RUNTIME_DIR))

    def test_unknown_cwd_only_matches_launcher(self):
        assert not discovery.is_akane_process(["uvicorn", "app.main:app"], cwd=None)


@dataclass
class _FakePsProcess:
    pid: int
    argv: list[str]
    workdir: str | None = "/"
    error: type[Exception] | None = None

    def cmdline(self):
        if self.error:
            raise self.error(self.pid)
        return self.argv

    def cwd(self):
        if self.workdir is None:
            raise psutil.AccessDenied(self.pid)
        return self.workdir


class TestFindAkaneProcesses:
    def test_selects_matching_processes_and_excludes_self(self):
        procs = [
            _FakePsProcess(1, [PY, "akane.py", "stop"]),
            _FakePsProcess(2, [PY, "akane.py", "dev"]),
            _FakePsProcess(3, ["uvicorn", "app.main:app"], str(RUNTIME_DIR)),
            _FakePsProcess(4, ["zsh"]),
        ]
        found = discovery.find_akane_processes(procs, exclude_pid=1)
        assert [p.pid for p in found] == [2, 3]

    @pytest.mark.parametrize("error", [psutil.NoSuchProcess, psutil.AccessDenied, psutil.ZombieProcess])
    def test_skips_processes_that_vanish_or_deny_access(self, error):
        procs = [_FakePsProcess(5, [], error=error), _FakePsProcess(6, [PY, "akane.py", "dev"])]
        assert [p.pid for p in discovery.find_akane_processes(procs, exclude_pid=0)] == [6]

    def test_cwd_access_denied_still_allows_launcher_match(self):
        procs = [_FakePsProcess(7, [PY, "akane.py", "dev"], workdir=None)]
        assert [p.pid for p in discovery.find_akane_processes(procs, exclude_pid=0)] == [7]


class TestFindRestartableLauncherArgs:
    def test_returns_args_of_the_running_launcher(self):
        procs = [_FakePsProcess(2, ["zsh"]), _FakePsProcess(3, [PY, "akane.py", "dev", "--voice"])]
        assert discovery.find_restartable_launcher_args(procs, exclude_pid=1) == ["dev", "--voice"]

    def test_ignores_own_process(self):
        procs = [_FakePsProcess(1, [PY, "akane.py", "dev"])]
        assert discovery.find_restartable_launcher_args(procs, exclude_pid=1) is None

    @pytest.mark.parametrize("args", [["stop"], ["restart"], []])
    def test_ignores_launchers_that_are_not_a_running_mode(self, args):
        # Regression: a concurrent `akane restart`/`akane stop` (or a bare
        # `akane.py`) used to be picked up and "restarted" into itself.
        procs = [_FakePsProcess(2, [PY, "akane.py", *args])]
        assert discovery.find_restartable_launcher_args(procs, exclude_pid=1) is None

    def test_skips_inaccessible_processes(self):
        procs = [_FakePsProcess(2, [], error=psutil.AccessDenied), _FakePsProcess(3, [PY, "akane.py", "start"])]
        assert discovery.find_restartable_launcher_args(procs, exclude_pid=1) == ["start"]


class _StoppableProcess:
    def __init__(
        self, pid: int, dies_on_terminate: bool = True, already_gone: bool = False, gone_before_kill: bool = False
    ):
        self.pid = pid
        self.dies_on_terminate = dies_on_terminate
        self.already_gone = already_gone
        self.gone_before_kill = gone_before_kill
        self.terminated = False
        self.killed = False

    def terminate(self):
        if self.already_gone:
            raise psutil.NoSuchProcess(self.pid)
        self.terminated = True

    def kill(self):
        if self.already_gone or self.gone_before_kill:
            raise psutil.NoSuchProcess(self.pid)
        self.killed = True


class TestStopProcesses:
    @pytest.fixture()
    def fake_wait_procs(self, monkeypatch):
        def wait_procs(procs, timeout):
            gone = [p for p in procs if p.dies_on_terminate or p.already_gone]
            alive = [p for p in procs if p not in gone]
            return gone, alive

        monkeypatch.setattr(discovery.psutil, "wait_procs", wait_procs)

    def test_terminates_every_process(self, fake_wait_procs):
        procs = [_StoppableProcess(1), _StoppableProcess(2)]
        assert discovery.stop_processes(procs) == []
        assert all(p.terminated and not p.killed for p in procs)

    def test_force_kills_processes_that_ignore_terminate(self, fake_wait_procs):
        stubborn = _StoppableProcess(2, dies_on_terminate=False)
        force_killed = discovery.stop_processes([_StoppableProcess(1), stubborn])
        assert force_killed == [stubborn]
        assert stubborn.killed

    def test_tolerates_processes_that_already_exited(self, fake_wait_procs):
        assert discovery.stop_processes([_StoppableProcess(1, already_gone=True)]) == []

    def test_tolerates_a_process_exiting_just_before_the_force_kill(self, fake_wait_procs):
        racer = _StoppableProcess(1, dies_on_terminate=False, gone_before_kill=True)
        assert discovery.stop_processes([racer]) == [racer]
        assert not racer.killed


def test_dann_processes_are_not_akane():
    # Review Focus: `akane stop` must never kill Dann, which also runs uvicorn
    # app.main:app from a directory named runtime/.
    dann_repo = "/Users/x/Git/r3dpnd/dann-of-thursday"
    assert not discovery.is_akane_process([PY, "dann.py", "dev"], dann_repo)
    assert not discovery.is_akane_process(["uvicorn", "app.main:app"], dann_repo + "/runtime")
    assert not discovery.is_akane_process(["node", "vite"], dann_repo + "/runtime/ui")
    assert discovery.is_akane_process(["uvicorn", "app.main:app"], str(RUNTIME_DIR))


@pytest.mark.parametrize("args", [["hunt"], ["schedule", "status"], ["jobs-app", "install"], ["stop"], ["restart"]])
def test_one_shot_commands_are_not_a_running_akane(args):
    # `akane stop` must not kill the nightly launchd hunt (review I-3).
    assert not discovery.is_akane_process([PY, "akane.py", *args], cwd="/anywhere")


@pytest.mark.parametrize("args", [["dev"], ["dev", "--speak"], ["code"], ["electron", "--voice"], ["start"]])
def test_long_running_commands_are_a_running_akane(args):
    assert discovery.is_akane_process([PY, "akane.py", *args], cwd="/anywhere")


def test_restart_never_picks_a_one_shot_command():
    procs = [_FakePsProcess(1, [PY, "akane.py", "hunt"]), _FakePsProcess(2, [PY, "akane.py", "dev", "--speak"])]
    assert discovery.find_restartable_launcher_args(procs, exclude_pid=0) == ["dev", "--speak"]
