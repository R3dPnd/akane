"""Unit tests for launcher.jobs_app — running pnd-job-search as a launchd agent."""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from launcher import jobs_app


def test_build_plist_runs_the_backend_from_its_dir_and_keeps_it_alive(tmp_path):
    binary = tmp_path / "backend" / "bin" / "pnd-job-search"
    plist = jobs_app.build_plist(binary, tmp_path / "backend", "/usr/bin:/Users/me/.local/bin", tmp_path / "logs")
    assert plist["Label"] == jobs_app.LABEL
    assert plist["ProgramArguments"] == [str(binary)]
    assert plist["WorkingDirectory"] == str(tmp_path / "backend")  # so the app finds ../.env
    assert plist["KeepAlive"] is True and plist["RunAtLoad"] is True
    assert "/.local/bin" in plist["EnvironmentVariables"]["PATH"]  # where `claude` lives
    assert plist["StandardErrorPath"].startswith(str(tmp_path / "logs"))


def test_merge_env_keeps_the_users_key_and_comments():
    merged = jobs_app.merge_env("# mine\nJOBS_API_KEY=abc\nPORT=1\n", {"PORT": "8080", "DATABASE_URL": "x"})
    assert merged.splitlines() == ["# mine", "JOBS_API_KEY=abc", "PORT=8080", "DATABASE_URL=x"]


def test_merge_env_on_an_empty_file():
    assert jobs_app.merge_env("", {"PORT": "8080"}).splitlines() == ["PORT=8080"]


@pytest.fixture()
def app_tree(tmp_path, monkeypatch):
    app = tmp_path / "pnd-job-search"
    (app / "backend").mkdir(parents=True)
    monkeypatch.setattr(jobs_app, "app_dir", lambda: app)
    monkeypatch.setattr(jobs_app, "PLIST_PATH", tmp_path / "agent.plist")
    monkeypatch.setattr(jobs_app, "healthy", lambda: False)
    monkeypatch.setattr(jobs_app.subprocess, "run",
                        lambda *a, **k: subprocess.CompletedProcess(a, 1, stdout="", stderr=""))
    return app


def test_status_never_prints_the_key(app_tree, capsys):
    (app_tree / ".env").write_text("JOBS_API_KEY=secret123\n")
    jobs_app.cmd_status()
    out = capsys.readouterr().out
    assert "JOBS_API_KEY: set" in out
    assert "secret123" not in out


def test_placeholder_key_reports_not_set(app_tree, capsys):
    (app_tree / ".env").write_text("JOBS_API_KEY=your_rapidapi_key_here\n")
    jobs_app.cmd_status()
    assert "JOBS_API_KEY: not set" in capsys.readouterr().out


def test_install_writes_owned_env_lines_and_the_plist(app_tree, monkeypatch):
    (app_tree / ".env").write_text("JOBS_API_KEY=abc\n")
    calls = []
    monkeypatch.setattr(jobs_app.subprocess, "run",
                        lambda argv, **k: calls.append(argv) or subprocess.CompletedProcess(argv, 0, "", ""))
    monkeypatch.setattr(jobs_app, "wait_healthy", lambda timeout: True)
    assert jobs_app.cmd_install() == 0
    env = (app_tree / ".env").read_text()
    assert "JOBS_API_KEY=abc" in env and "PORT=8080" in env
    assert f"UPLOADS_DIR={app_tree / 'uploads'}" in env
    assert "DATABASE_URL=postgres://" in env
    assert jobs_app.PLIST_PATH.exists()
    assert ["go", "build", "-o", "bin/pnd-job-search", "."] in calls
    assert any(c[:2] == ["launchctl", "bootstrap"] for c in calls)


def test_install_fails_cleanly_when_the_build_fails(app_tree, monkeypatch, capsys):
    monkeypatch.setattr(jobs_app.subprocess, "run",
                        lambda argv, **k: subprocess.CompletedProcess(argv, 2 if argv[0] == "go" else 0, "", "boom"))
    assert jobs_app.cmd_install() == 1
    assert "build failed" in capsys.readouterr().out.lower()


class _Resp:
    def __init__(self, status, payload):
        self.status_code, self._payload = status, payload

    def json(self):
        return self._payload


def test_load_resume_uploads_then_activates(tmp_path, monkeypatch):
    resume = tmp_path / "Resume.docx"
    resume.write_bytes(b"docx")
    monkeypatch.setattr(jobs_app, "base_url", lambda: "http://app/api/v1")
    calls = []

    def post(url, **kw):
        calls.append((url, sorted(kw.get("data", {}).items()), "files" in kw))
        return _Resp(201, {"id": "r1"}) if url.endswith("/resumes") else _Resp(200, {"id": "r1", "is_active": True})

    monkeypatch.setattr(jobs_app.requests, "post", post)
    assert jobs_app.cmd_load_resume(resume) == 0
    assert calls == [
        ("http://app/api/v1/resumes", [("label", "Base resume")], True),
        ("http://app/api/v1/resumes/r1/activate", [], False),
    ]


def test_load_resume_missing_file(tmp_path, capsys):
    assert jobs_app.cmd_load_resume(tmp_path / "nope.docx") == 1
    assert "not found" in capsys.readouterr().out


def test_base_url_and_app_dir_come_from_config(tmp_path, monkeypatch):
    from launcher import paths

    cfg = tmp_path / "config.yaml"
    cfg.write_text("job_search:\n  base_url: http://h:1/api/v1/\n  app_dir: ../apps/jobs\n")
    monkeypatch.setattr(paths, "CONFIG_PATH", cfg)
    monkeypatch.setattr(paths, "RUNTIME_DIR", tmp_path / "akane" / "runtime")
    assert jobs_app.base_url() == "http://h:1/api/v1"
    assert jobs_app.app_dir() == (tmp_path / "akane" / "apps" / "jobs").resolve()


@pytest.mark.parametrize("outcome, expected", [(200, True), (503, False), ("raise", False)])
def test_healthy(monkeypatch, outcome, expected):
    monkeypatch.setattr(jobs_app, "base_url", lambda: "http://app/api/v1")

    def get(url, timeout):
        if outcome == "raise":
            raise jobs_app.requests.ConnectionError()
        return _Resp(outcome, {})

    monkeypatch.setattr(jobs_app.requests, "get", get)
    assert jobs_app.healthy() is expected


def test_wait_healthy_gives_up(monkeypatch):
    monkeypatch.setattr(jobs_app, "healthy", lambda: False)
    monkeypatch.setattr(jobs_app.time, "sleep", lambda s: None)
    assert jobs_app.wait_healthy(0.01) is False


def test_wait_healthy_returns_as_soon_as_up(monkeypatch):
    monkeypatch.setattr(jobs_app, "healthy", lambda: True)
    assert jobs_app.wait_healthy(5) is True


def test_install_reports_a_launchctl_failure(app_tree, monkeypatch, capsys):
    def run(argv, **k):
        failed = argv[:2] == ["launchctl", "bootstrap"]
        return subprocess.CompletedProcess(argv, 5 if failed else 0, "", "Bootstrap failed: 5")
    monkeypatch.setattr(jobs_app.subprocess, "run", run)
    assert jobs_app.cmd_install() == 1
    assert "bootstrap failed" in capsys.readouterr().out.lower()


def test_install_reports_an_app_that_never_answers(app_tree, monkeypatch, capsys):
    monkeypatch.setattr(jobs_app.subprocess, "run", lambda argv, **k: subprocess.CompletedProcess(argv, 0, "", ""))
    monkeypatch.setattr(jobs_app, "wait_healthy", lambda timeout: False)
    assert jobs_app.cmd_install() == 1
    assert "didn't answer" in capsys.readouterr().out


def test_uninstall_removes_the_plist(app_tree):
    jobs_app.PLIST_PATH.write_text("x")
    assert jobs_app.cmd_uninstall() == 0
    assert not jobs_app.PLIST_PATH.exists()


def test_status_without_env_file_says_not_set(app_tree, capsys):
    assert jobs_app.cmd_status() == 1  # not healthy
    assert "JOBS_API_KEY: not set" in capsys.readouterr().out


@pytest.mark.parametrize("upload, activate", [(500, 200), (201, 404)])
def test_load_resume_reports_api_failures(tmp_path, monkeypatch, upload, activate):
    resume = tmp_path / "Resume.docx"
    resume.write_bytes(b"docx")
    monkeypatch.setattr(jobs_app, "base_url", lambda: "http://app/api/v1")
    monkeypatch.setattr(jobs_app.requests, "post",
                        lambda url, **kw: _Resp(upload, {"id": "r1"}) if url.endswith("/resumes") else _Resp(activate, {}))
    assert jobs_app.cmd_load_resume(resume) == 1
