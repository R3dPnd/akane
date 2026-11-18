"""Unit tests for launcher.remote — `akane remote on|off|status`: Akane's
dashboard on the user's other devices through Tailscale, never the open
network (the API itself listens on 127.0.0.1 only)."""

from __future__ import annotations

import json
import os
import subprocess
import time
from pathlib import Path

import pytest

from launcher import remote

TS = "/usr/local/bin/tailscale"
STATUS = json.dumps({"BackendState": "Running", "Self": {"DNSName": "akane-mac.tail1234.ts.net."}})


@pytest.fixture()
def fake(tmp_path, monkeypatch):
    ui = tmp_path / "ui"
    (ui / "src").mkdir(parents=True)
    (ui / "dist").mkdir()
    monkeypatch.setattr(remote.paths, "UI_DIR", ui)
    monkeypatch.setattr(remote.paths, "API_PORT", 8000)
    monkeypatch.setattr(remote, "tailscale_bin", lambda: TS)
    monkeypatch.setattr(remote.paths, "node_tool", lambda name: f"/bin/{name}")
    calls = []
    replies = {}

    def run(argv, **kw):
        calls.append(list(argv))
        code, out, err = replies.get(tuple(argv[1:3]), (0, "", ""))
        return subprocess.CompletedProcess(argv, code, out, err)

    monkeypatch.setattr(remote.subprocess, "run", run)
    replies[("status", "--json")] = (0, STATUS, "")
    return ui, calls, replies


def _touch(path: Path, age_s: float) -> None:
    path.write_text("x")
    t = time.time() - age_s
    os.utime(path, (t, t))


def test_the_ui_build_is_stale_without_a_dist(fake):
    ui, _, _ = fake
    assert remote.ui_is_stale(ui)


def test_the_ui_build_is_stale_when_a_source_is_newer(fake):
    ui, _, _ = fake
    _touch(ui / "dist" / "index.html", 100)
    _touch(ui / "src" / "App.tsx", 10)
    assert remote.ui_is_stale(ui)
    _touch(ui / "dist" / "index.html", 1)
    assert not remote.ui_is_stale(ui)


def test_on_builds_a_stale_ui_then_serves_the_local_api_and_prints_the_address(fake, capsys):
    ui, calls, _ = fake
    assert remote.cmd_on() == 0
    build, serve = ["/bin/npm", "run", "build"], [TS, "serve", "--bg", "http://127.0.0.1:8000"]
    assert calls.index(build) < calls.index(serve)  # sign-in is checked first, then build, then serve
    assert "https://akane-mac.tail1234.ts.net/" in capsys.readouterr().out


def test_on_skips_the_build_when_the_ui_is_current(fake):
    ui, calls, _ = fake
    _touch(ui / "src" / "App.tsx", 100)
    _touch(ui / "dist" / "index.html", 1)
    remote.cmd_on()
    assert ["/bin/npm", "run", "build"] not in calls


def test_on_stops_if_the_ui_build_fails(fake, capsys):
    _, calls, replies = fake
    replies[("run", "build")] = (1, "", "tsc: error")
    assert remote.cmd_on() == 1
    assert not any(c[1:2] == ["serve"] for c in calls)
    assert "build failed" in capsys.readouterr().out


def test_on_explains_signing_in_when_tailscale_is_logged_out(fake, capsys):
    _, calls, replies = fake
    replies[("status", "--json")] = (0, json.dumps({"BackendState": "NeedsLogin", "Self": {}}), "")
    assert remote.cmd_on() == 1
    assert not any(c[1:2] == ["serve"] for c in calls)
    assert "tailscale up" in capsys.readouterr().out


def test_on_reports_a_serve_failure(fake, capsys):
    _, _, replies = fake
    replies[("serve", "--bg")] = (1, "", "serve: HTTPS not enabled for this tailnet")
    assert remote.cmd_on() == 1
    assert "HTTPS not enabled" in capsys.readouterr().out


def test_without_tailscale_it_says_how_to_install(fake, monkeypatch, capsys):
    monkeypatch.setattr(remote, "tailscale_bin", lambda: None)
    for cmd in (remote.cmd_on, remote.cmd_off, remote.cmd_status):
        assert cmd() == 1
    assert "brew install --cask tailscale" in capsys.readouterr().out


def test_off_stops_serving(fake, capsys):
    _, calls, _ = fake
    assert remote.cmd_off() == 0
    assert calls[-1] == [TS, "serve", "--https=443", "off"]
    assert "off" in capsys.readouterr().out.lower()


def test_status_shows_tailscales_serve_status(fake, capsys):
    _, calls, replies = fake
    replies[("serve", "status")] = (0, "https://akane-mac.tail1234.ts.net (tailnet only)\n|-- / proxy http://127.0.0.1:8000", "")
    assert remote.cmd_status() == 0
    assert "tailnet only" in capsys.readouterr().out


def test_tailscale_bin_prefers_path_then_the_app_bundle(monkeypatch, tmp_path):
    monkeypatch.setattr(remote.shutil, "which", lambda name: "/opt/homebrew/bin/tailscale")
    assert remote.tailscale_bin() == "/opt/homebrew/bin/tailscale"
    app = tmp_path / "Tailscale"
    app.write_text("")
    monkeypatch.setattr(remote.shutil, "which", lambda name: None)
    monkeypatch.setattr(remote, "APP_CLI", app)
    assert remote.tailscale_bin() == str(app)
    monkeypatch.setattr(remote, "APP_CLI", tmp_path / "missing")
    assert remote.tailscale_bin() is None
