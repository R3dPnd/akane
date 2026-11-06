"""Unit tests for launcher.schedule — the nightly `akane hunt` launchd job."""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from launcher import schedule


def test_build_plist_runs_akane_hunt_daily_at_run_at(tmp_path):
    plist = schedule.build_plist(Path("/r/.venv/bin/python"), Path("/r/akane.py"), Path("/r"), "04:00",
                                 "/usr/bin:/Users/me/.local/bin", tmp_path)
    assert plist["Label"] == schedule.LABEL
    assert plist["ProgramArguments"] == ["/r/.venv/bin/python", "/r/akane.py", "hunt"]
    assert plist["StartCalendarInterval"] == {"Hour": 4, "Minute": 0}
    assert plist["RunAtLoad"] is False  # installing mustn't start a hunt
    assert plist["WorkingDirectory"] == "/r"
    assert plist["StandardOutPath"] == str(tmp_path / "akane-hunt.log")


@pytest.mark.parametrize("value, expected", [("04:00", (4, 0)), ("23:59", (23, 59)), ("7:05", (7, 5))])
def test_parse_run_at(value, expected):
    assert schedule.parse_run_at(value) == expected


@pytest.mark.parametrize("bad", ["4am", "25:00", "12:60", "", "noon"])
def test_parse_run_at_rejects_bad_times(bad):
    with pytest.raises(ValueError):
        schedule.parse_run_at(bad)


@pytest.fixture()
def fake_env(tmp_path, monkeypatch):
    monkeypatch.setattr(schedule, "PLIST_PATH", tmp_path / "agent.plist")
    monkeypatch.setattr(schedule, "LOG_DIR", tmp_path / "logs")
    monkeypatch.setattr(schedule, "run_at", lambda: "04:30")
    calls = []
    monkeypatch.setattr(schedule.subprocess, "run",
                        lambda argv, **k: calls.append(argv) or subprocess.CompletedProcess(argv, 0, "", ""))
    return calls


def test_install_bootstraps_the_agent(fake_env, capsys):
    assert schedule.cmd_install() == 0
    assert schedule.PLIST_PATH.exists()
    assert any(c[:2] == ["launchctl", "bootstrap"] for c in fake_env)
    assert "04:30" in capsys.readouterr().out


def test_install_reports_a_bad_run_at(fake_env, monkeypatch, capsys):
    monkeypatch.setattr(schedule, "run_at", lambda: "4am")
    assert schedule.cmd_install() == 1
    assert "run_at" in capsys.readouterr().out


def test_install_reports_a_launchctl_failure(fake_env, monkeypatch, capsys):
    monkeypatch.setattr(schedule.subprocess, "run", lambda argv, **k: subprocess.CompletedProcess(
        argv, 5 if argv[:2] == ["launchctl", "bootstrap"] else 0, "", "Bootstrap failed"))
    assert schedule.cmd_install() == 1


def test_uninstall_removes_the_plist(fake_env):
    schedule.PLIST_PATH.write_text("x")
    assert schedule.cmd_uninstall() == 0
    assert not schedule.PLIST_PATH.exists()


def test_status_reports_not_loaded(fake_env, monkeypatch, capsys):
    monkeypatch.setattr(schedule.subprocess, "run", lambda argv, **k: subprocess.CompletedProcess(argv, 113, "", ""))
    assert schedule.cmd_status() == 1
    assert "not loaded" in capsys.readouterr().out


def test_status_shows_the_last_log_line(fake_env, capsys):
    schedule.LOG_DIR.mkdir()
    (schedule.LOG_DIR / "akane-hunt.log").write_text("starting\n8 new lead(s) → /x/2026-11-06.md\n")
    assert schedule.cmd_status() == 0
    out = capsys.readouterr().out
    assert "loaded" in out and "04:30" in out and "8 new lead(s)" in out


def test_run_at_reads_config(tmp_path, monkeypatch):
    from launcher import paths

    cfg = tmp_path / "config.yaml"
    cfg.write_text("job_hunt:\n  run_at: '05:15'\n")
    monkeypatch.setattr(paths, "CONFIG_PATH", cfg)
    assert schedule.run_at() == "05:15"
    cfg.write_text("ollama: {}\n")
    assert schedule.run_at() == "04:00"
