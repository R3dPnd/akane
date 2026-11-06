"""Unit tests for launcher.commands — the orchestration behind each subcommand.

Process spawning, readiness polling, and process discovery are all replaced
with fakes here; the integration suite covers them for real.
"""

from __future__ import annotations

import pytest

from launcher import commands, discovery, paths, preflight, processes, readiness
from launcher.supervisor import Supervisor


class _TestSupervisor(Supervisor):
    """Real supervisor logic, minus touching the test runner's signal handlers."""

    instances: list[_TestSupervisor] = []

    def __init__(self):
        super().__init__(poll_interval=0.001, grace_period=0.01)
        self.signal_handlers_installed = False
        _TestSupervisor.instances.append(self)

    def install_signal_handlers(self):
        self.signal_handlers_installed = True


@pytest.fixture()
def harness(monkeypatch, fake_process_factory):
    """Wire commands up to fakes and expose what they did."""
    _TestSupervisor.instances.clear()

    class Harness:
        api = fake_process_factory("api", returncode=None)
        ui = fake_process_factory("ui", returncode=None)
        window = fake_process_factory("window")
        api_ready = True
        ui_ready = True
        spawned: list[tuple] = []
        opened_urls: list[str] = []
        preflight_ok = True
        preflight_calls: list[tuple] = []

        @property
        def supervisor(self) -> _TestSupervisor:
            return _TestSupervisor.instances[-1]

    h = Harness()

    def spawn_api(voice, capture_output=True, speak=False):
        h.spawned.append(("api", voice, capture_output) + (("speak",) if speak else ()))
        # Let the session end right away once the supervisor starts waiting.
        h.api.returncode = 0
        return h.api

    def spawn_npm_script(script):
        h.spawned.append(("npm", script))
        return h.ui

    def spawn_electron_window():
        h.spawned.append(("electron-window",))
        return h.window

    def wait_until_serving(url, timeout, should_abort=None, interval=0.3):
        return h.api_ready if url == paths.api_health_url(paths.API_PORT) else h.ui_ready

    monkeypatch.setattr(processes, "spawn_api", spawn_api)
    monkeypatch.setattr(processes, "spawn_npm_script", spawn_npm_script)
    monkeypatch.setattr(processes, "spawn_electron_window", spawn_electron_window)
    monkeypatch.setattr(processes, "forward_output", lambda proc, prefix, out=None: [])
    monkeypatch.setattr(readiness, "wait_until_serving", wait_until_serving)
    monkeypatch.setattr(commands.webbrowser, "open", h.opened_urls.append)
    monkeypatch.setattr(commands, "Supervisor", _TestSupervisor)
    monkeypatch.setattr(commands, "run_in_background", lambda fn, *args: fn(*args))
    monkeypatch.setattr(preflight, "run",
                        lambda voice, ui, speak=False, electron=False: h.preflight_calls.append(
                            (voice, ui) + (("speak",) if speak else ()) + (("electron",) if electron else ())) or h.preflight_ok)
    return h


class TestCmdDev:
    def test_starts_api_then_vite_and_opens_a_browser(self, harness):
        assert commands.cmd_dev(voice=False) == 0
        assert harness.spawned == [("api", False, True), ("npm", "dev")]
        assert harness.opened_urls == [paths.ui_url(paths.UI_PORT)]
        assert harness.supervisor.signal_handlers_installed

    def test_voice_mode_opens_an_electron_window_instead(self, harness):
        commands.cmd_dev(voice=True)
        assert harness.spawned == [("api", True, True), ("npm", "dev"), ("electron-window",)]
        assert harness.opened_urls == []

    def test_electron_window_is_stopped_with_everything_else(self, harness):
        commands.cmd_dev(voice=True)
        # Regression: the window used to be spawned untracked and orphaned on exit.
        assert harness.window.terminated

    def test_ui_is_stopped_when_the_api_exits(self, harness):
        commands.cmd_dev(voice=False)
        assert harness.ui.terminated

    def test_aborts_without_starting_the_ui_if_the_api_never_comes_up(self, harness):
        harness.api_ready = False
        assert commands.cmd_dev(voice=False) == 1
        assert ("npm", "dev") not in harness.spawned
        assert harness.api.terminated or harness.api.returncode is not None

    def test_skips_the_browser_if_the_ui_never_comes_up(self, harness):
        harness.ui_ready = False
        commands.cmd_dev(voice=False)
        assert harness.opened_urls == []


class TestCmdElectron:
    def test_starts_api_then_the_electron_dev_script(self, harness):
        assert commands.cmd_electron(voice=False) == 0
        assert harness.spawned == [("api", False, True), ("npm", "electron:dev")]
        assert harness.opened_urls == []

    def test_passes_voice_through_to_the_api(self, harness):
        commands.cmd_electron(voice=True)
        assert harness.spawned[0] == ("api", True, True)

    def test_aborts_if_the_api_never_comes_up(self, harness):
        harness.api_ready = False
        assert commands.cmd_electron(voice=False) == 1
        assert len(harness.spawned) == 1


class TestCmdStart:
    def test_runs_the_api_with_voice_attached_to_the_terminal(self, harness):
        assert commands.cmd_start() == 0
        assert harness.spawned == [("api", True, False)]
        assert harness.supervisor.signal_handlers_installed

    def test_returns_the_api_exit_code(self, harness, monkeypatch):
        def crashing_api(voice, capture_output=True):
            harness.api.returncode = 7
            return harness.api

        monkeypatch.setattr(processes, "spawn_api", crashing_api)
        assert commands.cmd_start() == 7


class TestCmdStop:
    @pytest.fixture()
    def stop_harness(self, monkeypatch):
        state = {"found": [], "force_killed": [], "stopped": None}
        monkeypatch.setattr(discovery, "list_processes", lambda: ["sentinel"])
        monkeypatch.setattr(discovery, "find_akane_processes", lambda procs, exclude_pid: state["found"])

        def stop_processes(procs, timeout=5.0):
            state["stopped"] = procs
            return state["force_killed"]

        monkeypatch.setattr(discovery, "stop_processes", stop_processes)
        return state

    class _Proc:
        def __init__(self, pid):
            self.pid = pid

    def test_reports_nothing_running(self, stop_harness, capsys):
        assert commands.cmd_stop() == 0
        assert "Nothing running" in capsys.readouterr().out
        assert stop_harness["stopped"] is None

    def test_stops_every_matching_process(self, stop_harness, capsys):
        stop_harness["found"] = [self._Proc(10), self._Proc(11)]
        assert commands.cmd_stop() == 0
        assert [p.pid for p in stop_harness["stopped"]] == [10, 11]
        out = capsys.readouterr().out
        assert "Stopping 2 process(es): [10, 11]" in out
        assert "Force-killed" not in out

    def test_reports_force_killed_processes(self, stop_harness, capsys):
        stubborn = self._Proc(11)
        stop_harness["found"] = [self._Proc(10), stubborn]
        stop_harness["force_killed"] = [stubborn]
        commands.cmd_stop()
        assert "Force-killed 1 process(es) that didn't exit cleanly: [11]" in capsys.readouterr().out


class TestCmdRestart:
    @pytest.fixture()
    def restart_harness(self, monkeypatch):
        state = {"launcher_args": None, "stopped": 0, "relaunched": None}
        monkeypatch.setattr(discovery, "list_processes", lambda: [])
        monkeypatch.setattr(
            discovery, "find_restartable_launcher_args", lambda procs, exclude_pid: state["launcher_args"]
        )
        monkeypatch.setattr(commands, "cmd_stop", lambda: state.__setitem__("stopped", state["stopped"] + 1) or 0)
        monkeypatch.setattr(commands.time, "sleep", lambda _s: None)
        return state

    def _relaunch(self, state):
        def relaunch(args):
            state["relaunched"] = args
            return 0

        return relaunch

    def test_does_nothing_when_no_launcher_is_running(self, restart_harness, capsys):
        assert commands.cmd_restart(relaunch=self._relaunch(restart_harness)) == 1
        assert restart_harness["stopped"] == 0
        assert restart_harness["relaunched"] is None
        assert "Nothing running to restart" in capsys.readouterr().out

    def test_stops_then_relaunches_with_the_same_args(self, restart_harness):
        restart_harness["launcher_args"] = ["dev", "--voice"]
        assert commands.cmd_restart(relaunch=self._relaunch(restart_harness)) == 0
        assert restart_harness["stopped"] == 1
        assert restart_harness["relaunched"] == ["dev", "--voice"]


class TestPreflight:
    @pytest.mark.parametrize("run, expected_call", [
        (lambda: commands.cmd_dev(voice=True), (True, True, "electron")),
        (lambda: commands.cmd_dev(voice=False), (False, True)),
        (lambda: commands.cmd_electron(voice=False), (False, True, "electron")),
        (lambda: commands.cmd_start(), (True, False)),
    ])
    def test_each_launch_runs_preflight_first(self, harness, run, expected_call):
        harness.preflight_calls.clear()
        run()
        assert harness.preflight_calls == [expected_call]

    @pytest.mark.parametrize("run", [
        lambda: commands.cmd_dev(voice=True),
        lambda: commands.cmd_electron(voice=True),
        lambda: commands.cmd_start(),
    ])
    def test_a_preflight_error_stops_before_spawning_anything(self, harness, run):
        harness.preflight_ok = False
        harness.spawned.clear()
        assert run() == 1
        assert harness.spawned == []


class TestSpeakMode:
    def test_dev_speak_runs_speak_only_api_and_opens_a_browser(self, harness):
        harness.spawned.clear()
        harness.preflight_calls.clear()
        assert commands.cmd_dev(speak=True) == 0
        assert harness.spawned == [("api", False, True, "speak"), ("npm", "dev")]
        assert harness.preflight_calls == [(False, True, "speak")]  # browser tab, no Electron
        assert harness.opened_urls[-1] == paths.ui_url(paths.UI_PORT)

    def test_electron_speak_runs_speak_only_api(self, harness):
        harness.spawned.clear()
        assert commands.cmd_electron(speak=True) == 0
        assert harness.spawned[0] == ("api", False, True, "speak")


class TestJobsApp:
    def test_actions_dispatch_to_jobs_app(self, monkeypatch):
        from launcher import jobs_app

        monkeypatch.setattr(jobs_app, "cmd_install", lambda: 7)
        monkeypatch.setattr(jobs_app, "cmd_status", lambda: 8)
        assert commands.cmd_jobs_app("install") == 7
        assert commands.cmd_jobs_app("status") == 8

    def test_load_resume_expands_the_path(self, monkeypatch):
        from pathlib import Path

        from launcher import jobs_app

        seen = []
        monkeypatch.setattr(jobs_app, "cmd_load_resume", lambda p: seen.append(p) or 0)
        assert commands.cmd_jobs_app("load-resume", resume="~/Resume.docx") == 0
        assert seen == [Path.home() / "Resume.docx"]

    def test_load_resume_needs_a_path(self, capsys):
        assert commands.cmd_jobs_app("load-resume") == 2
        assert "usage" in capsys.readouterr().out


class TestHunt:
    def test_hunt_runs_the_runtime_module_with_the_persona_config(self, monkeypatch):
        import subprocess

        calls = []

        def run(argv, **kw):
            calls.append((argv, kw))
            return subprocess.CompletedProcess(argv, 0)

        monkeypatch.setattr(commands.subprocess, "run", run)
        assert commands.cmd_hunt() == 0
        ((argv, kw),) = calls
        assert argv == [str(paths.VENV_BIN / "python"), "-m", "integrations.job_search", "hunt"]
        assert kw["cwd"] == str(paths.RUNTIME_DIR)
        assert kw["env"]["PND_CONFIG_PATH"] == str(paths.CONFIG_PATH)

    def test_hunt_returns_the_hunts_exit_code(self, monkeypatch):
        import subprocess

        monkeypatch.setattr(commands.subprocess, "run", lambda argv, **kw: subprocess.CompletedProcess(argv, 3))
        assert commands.cmd_hunt() == 3


def test_schedule_actions_dispatch(monkeypatch):
    from launcher import schedule

    monkeypatch.setattr(schedule, "cmd_install", lambda: 7)
    monkeypatch.setattr(schedule, "cmd_uninstall", lambda: 8)
    monkeypatch.setattr(schedule, "cmd_status", lambda: 9)
    assert [commands.cmd_schedule(a) for a in ("install", "uninstall", "status")] == [7, 8, 9]
