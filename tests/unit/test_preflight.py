"""Unit tests for launcher.preflight — what's checked before Akane starts, and
what the user is told when something is missing."""

from __future__ import annotations

import socket
import subprocess

import pytest

from launcher import paths, preflight

API, UI = 8000, 3000


@pytest.fixture()
def runtime(tmp_path, monkeypatch):
    """A fake runtime/ dir with every model and server file in place, so each
    test removes just the one thing it's about."""
    rt = tmp_path / "repo" / "runtime"
    rt.mkdir(parents=True)
    models = tmp_path / "repo" / "models"
    (models / "piper").mkdir(parents=True)
    (models / "ok_akane.onnx").write_bytes(b"")
    (models / "piper" / "en_GB-alba-medium.onnx").write_bytes(b"")
    notes = tmp_path / "pnd-notes" / "server"
    notes.mkdir(parents=True)
    (notes / "pnd-notes.mjs").write_text("")
    monkeypatch.setattr(paths, "RUNTIME_DIR", rt)
    return rt


def _config():
    return {
        "wake_word": {"model": "../models/ok_akane.onnx"},
        "tts": {"voice_model": "../models/piper/en_GB-alba-medium"},
        "ollama": {"model": "akane-router"},
        "mcp": {"servers": [
            {"name": "claude", "command": "../.venv/bin/python", "args": ["-m", "integrations.servers.claude_server"]},
            {"name": "pnd_notes", "command": "node", "args": ["../../pnd-notes/server/pnd-notes.mjs"]},
        ]},
    }


def _check(config=None, voice=True, busy=(), models=("akane-router:latest",), speak=False):
    return preflight.check(
        voice,
        speak=speak,
        config=_config() if config is None else config,
        ports=[API, UI],
        port_in_use=lambda port: port in busy,
        ollama_models=lambda: None if models is None else list(models),
    )


def test_clean_machine_has_no_problems(runtime):
    assert _check() == []


def test_busy_port_is_an_error_suggesting_dann_stop(runtime):
    (problem,) = _check(busy={API})
    assert problem.level == "error"
    assert "8000" in problem.message
    assert "dann stop" in problem.fix


def test_missing_wake_model_is_an_error_with_voice(runtime):
    (runtime.parent / "models" / "ok_akane.onnx").unlink()
    (problem,) = _check()
    assert problem.level == "error"
    assert "ok_akane.onnx" in problem.message
    assert "scripts/train_wakeword.sh" in problem.fix


def test_builtin_wake_word_name_needs_no_file(runtime):
    config = _config()
    config["wake_word"]["model"] = "hey_jarvis"
    assert _check(config) == []


def test_missing_piper_voice_is_an_error_with_voice(runtime):
    (runtime.parent / "models" / "piper" / "en_GB-alba-medium.onnx").unlink()
    (problem,) = _check()
    assert problem.level == "error"
    assert "en_GB-alba-medium" in problem.message
    assert "scripts/setup.sh" in problem.fix


def test_voice_checks_skipped_without_voice(runtime):
    (runtime.parent / "models" / "ok_akane.onnx").unlink()
    (runtime.parent / "models" / "piper" / "en_GB-alba-medium.onnx").unlink()
    assert _check(voice=False) == []


def test_router_model_not_built_is_a_warning(runtime):
    (problem,) = _check(models=["qwen2.5:7b-instruct"])
    assert problem.level == "warning"
    assert "akane-router" in problem.message
    assert "scripts/build_router.sh" in problem.fix


def test_ollama_not_installed_is_a_warning(runtime):
    (problem,) = _check(models=None)
    assert problem.level == "warning"
    assert "ollama" in problem.message.lower()
    assert "brew install ollama" in problem.fix


def test_missing_node_server_script_is_a_warning(runtime):
    (runtime.parent.parent / "pnd-notes" / "server" / "pnd-notes.mjs").unlink()
    (problem,) = _check()
    assert problem.level == "warning"
    assert "pnd_notes" in problem.message
    assert "git clone" in problem.fix


def test_report_returns_false_on_error_true_on_warnings_only(capsys):
    warning = preflight.Problem("warning", "router missing", "build it")
    error = preflight.Problem("error", "port busy", "dann stop")
    assert preflight.report([warning]) is True
    assert preflight.report([warning, error]) is False
    out = capsys.readouterr().out
    assert "[akane] error: port busy — fix: dann stop" in out
    assert "[akane] warning: router missing — fix: build it" in out


def test_speak_mode_needs_the_voice_but_not_the_wake_model(runtime):
    (runtime.parent / "models" / "ok_akane.onnx").unlink()
    assert _check(voice=False, speak=True) == []
    (runtime.parent / "models" / "piper" / "en_GB-alba-medium.onnx").unlink()
    (problem,) = _check(voice=False, speak=True)
    assert "en_GB-alba-medium" in problem.message


class TestRealProbes:
    def test_port_in_use_sees_a_bound_socket(self):
        with socket.socket() as s:
            s.bind(("127.0.0.1", 0))
            s.listen()
            assert preflight.port_in_use(s.getsockname()[1]) is True

    def test_free_port_is_not_in_use(self):
        with socket.socket() as s:
            s.bind(("127.0.0.1", 0))
            port = s.getsockname()[1]
        assert preflight.port_in_use(port) is False

    def test_ollama_models_parses_ollama_list(self, monkeypatch):
        listing = "NAME                  ID      SIZE    MODIFIED\nakane-router:latest   abc     4.7 GB  now\nqwen2.5:7b-instruct   def     4.7 GB  now\n"
        monkeypatch.setattr(preflight.subprocess, "run",
                            lambda *a, **k: subprocess.CompletedProcess(a, 0, stdout=listing, stderr=""))
        assert preflight.ollama_models() == ["akane-router:latest", "qwen2.5:7b-instruct"]

    def test_ollama_models_is_none_without_ollama(self, monkeypatch):
        def missing(*a, **k):
            raise FileNotFoundError("ollama")
        monkeypatch.setattr(preflight.subprocess, "run", missing)
        assert preflight.ollama_models() is None


class TestRun:
    def test_run_checks_both_ports_for_dev(self, monkeypatch):
        seen = {}

        def fake_check(voice, *, speak, config, ports, port_in_use, ollama_models):
            seen.update(voice=voice, ports=ports)
            return []

        monkeypatch.setattr(preflight, "check", fake_check)
        monkeypatch.setattr(preflight, "_load_config", lambda: {})
        assert preflight.run(voice=True, ui=True) is True
        assert seen == {"voice": True, "ports": [paths.API_PORT, paths.UI_PORT]}

    def test_run_checks_only_the_api_port_without_ui(self, monkeypatch):
        seen = {}
        monkeypatch.setattr(preflight, "check", lambda voice, **kw: seen.update(kw) or [])
        monkeypatch.setattr(preflight, "_load_config", lambda: {})
        preflight.run(voice=True, ui=False)
        assert seen["ports"] == [paths.API_PORT]

    def test_run_passes_speak_mode_to_check(self, monkeypatch):
        seen = {}
        monkeypatch.setattr(preflight, "check", lambda voice, **kw: seen.update(kw) or [])
        monkeypatch.setattr(preflight, "_load_config", lambda: {})
        preflight.run(voice=False, ui=True, speak=True)
        assert seen["speak"] is True

    def test_run_fails_on_an_error(self, monkeypatch, capsys):
        monkeypatch.setattr(preflight, "check", lambda voice, **kw: [preflight.Problem("error", "x", "y")])
        monkeypatch.setattr(preflight, "_load_config", lambda: {})
        assert preflight.run(voice=False, ui=False) is False

    def test_load_config_reads_the_persona_config(self, tmp_path, monkeypatch):
        cfg = tmp_path / "config.yaml"
        cfg.write_text("ollama: {model: akane-router}\n")
        monkeypatch.setattr(paths, "CONFIG_PATH", cfg)
        assert preflight._load_config()["ollama"]["model"] == "akane-router"

    def test_load_config_is_empty_without_a_config(self, tmp_path, monkeypatch):
        monkeypatch.setattr(paths, "CONFIG_PATH", tmp_path / "nope.yaml")
        assert preflight._load_config() == {}
