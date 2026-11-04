"""Unit tests for launcher.processes — how the API/UI child processes are built.

`subprocess.Popen` is replaced with a recorder so these tests check the exact
command, cwd, and environment each child gets, without launching anything.
"""

from __future__ import annotations

import io

import pytest

from launcher import paths, processes


@pytest.fixture()
def popen_calls(monkeypatch, fake_process_factory):
    calls = []

    def fake_popen(cmd, **kwargs):
        calls.append({"cmd": cmd, **kwargs})
        return fake_process_factory(name=str(cmd))

    monkeypatch.setattr(processes.subprocess, "Popen", fake_popen)
    return calls


class TestBuildApiEnv:
    def test_speak_mode_runs_the_voice_pipeline_without_the_mic(self):
        env = processes.build_api_env(voice=False, speak=True, base_env={"NO_VOICE": "1"})
        assert "NO_VOICE" not in env
        assert env["PND_VOICE_MODE"] == "speak"

    def test_listening_voice_clears_an_inherited_speak_mode(self):
        env = processes.build_api_env(voice=True, base_env={"PND_VOICE_MODE": "speak"})
        assert "PND_VOICE_MODE" not in env

    def test_no_voice_ignores_speak_mode(self):
        env = processes.build_api_env(voice=False, base_env={"PND_VOICE_MODE": "speak"})
        assert env["NO_VOICE"] == "1"
        assert "PND_VOICE_MODE" not in env

    def test_api_env_points_runtime_at_akane_config_and_ports(self):
        env = processes.build_api_env(voice=True, base_env={"DANN_CONFIG_PATH": "/x", "NO_VOICE": "1"})
        assert env["PND_CONFIG_PATH"] == str(paths.CONFIG_PATH)
        assert env["PND_API_PORT"] == str(paths.API_PORT)
        assert env["PND_UI_PORT"] == str(paths.UI_PORT)
        assert env["PND_PERSONA_NAME"] == paths.PERSONA_NAME
        assert "NO_VOICE" not in env

    def test_points_the_runtime_at_this_repos_config(self):
        env = processes.build_api_env(voice=True, base_env={})
        assert env["PND_CONFIG_PATH"] == str(paths.CONFIG_PATH)

    def test_disables_voice_unless_requested(self):
        assert processes.build_api_env(voice=False, base_env={})["NO_VOICE"] == "1"
        assert "NO_VOICE" not in processes.build_api_env(voice=True, base_env={})

    def test_voice_mode_clears_an_inherited_no_voice(self):
        # Otherwise `NO_VOICE=1` exported in the shell would silently win over --voice.
        assert "NO_VOICE" not in processes.build_api_env(voice=True, base_env={"NO_VOICE": "1"})

    def test_keeps_the_parent_environment_and_unbuffers_output(self):
        env = processes.build_api_env(voice=False, base_env={"PATH": "/bin"})
        assert env["PATH"] == "/bin"
        assert env["PYTHONUNBUFFERED"] == "1"

    def test_does_not_mutate_the_base_env(self):
        base = {"PATH": "/bin"}
        processes.build_api_env(voice=False, base_env=base)
        assert base == {"PATH": "/bin"}


class TestSpawnApi:
    def test_runs_uvicorn_from_the_runtime_dir(self, popen_calls):
        processes.spawn_api(voice=False)

        (call,) = popen_calls
        assert call["cmd"] == [str(paths.VENV_UVICORN), "app.main:app", "--host", "0.0.0.0", "--port", str(paths.API_PORT)]
        assert call["cwd"] == str(paths.RUNTIME_DIR)
        assert call["env"]["NO_VOICE"] == "1"

    def test_captures_output_by_default(self, popen_calls):
        processes.spawn_api(voice=False)
        assert popen_calls[0]["stdout"] is processes.subprocess.PIPE
        assert popen_calls[0]["text"] is True

    def test_can_inherit_the_terminal_instead(self, popen_calls):
        processes.spawn_api(voice=True, capture_output=False)
        assert "stdout" not in popen_calls[0]


class TestSpawnNpmScript:
    def test_runs_the_script_from_the_ui_dir(self, popen_calls):
        processes.spawn_npm_script("dev")
        (call,) = popen_calls
        assert call["cmd"] == [paths.node_tool("npm"), "run", "dev"]
        assert call["cwd"] == str(paths.UI_DIR)
        assert call["stderr"] is processes.subprocess.STDOUT


class TestSpawnNpmScriptEnv:
    def test_vite_gets_persona_ports(self, popen_calls):
        processes.spawn_npm_script("dev")
        (call,) = popen_calls
        assert call["env"]["PND_API_PORT"] == str(paths.API_PORT)
        assert call["env"]["PND_UI_PORT"] == str(paths.UI_PORT)


class TestSpawnElectronWindow:
    def test_launches_fullscreen_dev_mode_electron(self, popen_calls):
        processes.spawn_electron_window()
        (call,) = popen_calls
        assert call["cmd"] == [paths.node_tool("npx"), "electron", "."]
        assert call["cwd"] == str(paths.UI_DIR)
        assert call["env"]["NODE_ENV"] == "development"
        assert call["env"]["PND_FULLSCREEN"] == "1"

    def test_electron_gets_persona_ports_and_name(self, popen_calls):
        processes.spawn_electron_window()
        (call,) = popen_calls
        assert call["env"]["PND_API_PORT"] == str(paths.API_PORT)
        assert call["env"]["PND_UI_PORT"] == str(paths.UI_PORT)
        assert call["env"]["PND_PERSONA_NAME"] == paths.PERSONA_NAME


class TestStreamLines:
    def test_prefixes_every_line(self):
        out = io.StringIO()
        processes.stream_lines(io.StringIO("one\ntwo\n"), "[api]", out=out)
        assert out.getvalue() == "[api] one\n[api] two\n"

    def test_stops_quietly_when_the_pipe_closes(self):
        class ClosedPipe:
            def __iter__(self):
                raise ValueError("I/O operation on closed file")

        out = io.StringIO()
        processes.stream_lines(ClosedPipe(), "[api]", out=out)
        assert out.getvalue() == ""


class TestForwardOutput:
    def test_forwards_stdout_and_stderr(self, fake_process_factory):
        proc = fake_process_factory(stdout=["out\n"], stderr=["err\n"])
        out = io.StringIO()
        for thread in processes.forward_output(proc, "[x]", out=out):
            thread.join(timeout=1)
        assert sorted(out.getvalue().splitlines()) == ["[x] err", "[x] out"]

    def test_skips_streams_that_were_not_captured(self, fake_process_factory):
        proc = fake_process_factory(stdout=["out\n"], stderr=None)
        assert len(processes.forward_output(proc, "[x]", out=io.StringIO())) == 1


def test_spawn_api_passes_speak_mode_through(popen_calls):
    processes.spawn_api(voice=False, speak=True)
    (call,) = popen_calls
    assert call["env"]["PND_VOICE_MODE"] == "speak"
