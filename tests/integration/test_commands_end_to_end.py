"""`akane dev` / `akane start` end to end, with stand-in uvicorn and npm executables.

The fakes are real processes serving real HTTP on ephemeral ports, so this
exercises the actual spawn → health-check → start UI → open browser →
shutdown sequence — just without the runtime's heavy dependencies.
"""

from __future__ import annotations

import json
import time

import pytest

from launcher import commands, paths
from launcher.supervisor import Supervisor

from .conftest import is_running, posix_only

pytestmark = [pytest.mark.integration, posix_only]

# Serves 200 on /api/v1/health at --port, records how it was launched to
# $FAKE_RECORD, then exits with $FAKE_EXIT_CODE after $FAKE_LIFETIME seconds.
FAKE_UVICORN = """\
import http.server, json, os, sys, threading, time

port = int(sys.argv[sys.argv.index("--port") + 1])
with open(os.environ["FAKE_RECORD"], "w") as f:
    json.dump({"argv": sys.argv[1:], "cwd": os.getcwd(),
               "NO_VOICE": os.environ.get("NO_VOICE"),
               "PND_CONFIG_PATH": os.environ.get("PND_CONFIG_PATH")}, f)

class Health(http.server.BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200 if self.path == "/api/v1/health" else 404)
        self.end_headers()
    def log_message(self, *args):
        pass

if float(os.environ.get("FAKE_LIFETIME", "0")) > 0:
    server = http.server.HTTPServer(("127.0.0.1", port), Health)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    print("fake api up", flush=True)
    time.sleep(float(os.environ["FAKE_LIFETIME"]))
sys.exit(int(os.environ.get("FAKE_EXIT_CODE", "0")))
"""

# `npm run dev` stand-in: serves 200 at $FAKE_UI_PORT until terminated.
FAKE_NPM = """\
import http.server, os, sys

with open(os.environ["FAKE_UI_PIDFILE"], "w") as f:
    f.write(str(os.getpid()))

class Ok(http.server.BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.end_headers()
    def log_message(self, *args):
        pass

http.server.HTTPServer(("127.0.0.1", int(os.environ["FAKE_UI_PORT"])), Ok).serve_forever()
"""


@pytest.fixture()
def fake_runtime(monkeypatch, tmp_path, make_script, free_port):
    """Point the launcher at fake uvicorn/npm executables and free ports."""
    api_port, ui_port = free_port(), free_port()
    record, ui_pidfile = tmp_path / "api.json", tmp_path / "ui.pid"
    fake_npm = make_script("npm", FAKE_NPM)

    monkeypatch.setattr(paths, "VENV_UVICORN", make_script("uvicorn", FAKE_UVICORN))
    monkeypatch.setattr(paths, "API_PORT", api_port)
    monkeypatch.setattr(paths, "UI_PORT", ui_port)
    monkeypatch.setattr(paths, "node_tool", lambda name: str(fake_npm) if name == "npm" else name)
    monkeypatch.setenv("FAKE_RECORD", str(record))
    monkeypatch.setenv("FAKE_UI_PORT", str(ui_port))
    monkeypatch.setenv("FAKE_UI_PIDFILE", str(ui_pidfile))
    monkeypatch.setenv("FAKE_LIFETIME", "3")
    monkeypatch.delenv("NO_VOICE", raising=False)
    # Real signal handlers would hijack Ctrl+C for the whole pytest run.
    monkeypatch.setattr(Supervisor, "install_signal_handlers", lambda self: None)

    opened = []
    monkeypatch.setattr(commands.webbrowser, "open", opened.append)

    class FakeRuntime:
        browser_urls = opened

        @staticmethod
        def api_launch() -> dict:
            return json.loads(record.read_text())

        @staticmethod
        def ui_pid() -> int:
            return int(ui_pidfile.read_text())

    return FakeRuntime


def test_dev_starts_api_and_ui_opens_the_browser_and_cleans_up(fake_runtime):
    exit_code = commands.cmd_dev(voice=False)

    assert exit_code == 0
    launch = fake_runtime.api_launch()
    assert launch["cwd"] == str(paths.RUNTIME_DIR)
    assert launch["NO_VOICE"] == "1"
    assert launch["PND_CONFIG_PATH"] == str(paths.CONFIG_PATH)
    assert launch["argv"][0] == "app.main:app"
    assert fake_runtime.browser_urls == [paths.ui_url(paths.UI_PORT)]
    # The API exiting ended the session, and took the UI down with it.
    assert not is_running(fake_runtime.ui_pid())


def test_dev_aborts_fast_when_the_api_crashes_on_startup(fake_runtime, monkeypatch, tmp_path):
    monkeypatch.setenv("FAKE_LIFETIME", "0")
    monkeypatch.setenv("FAKE_EXIT_CODE", "1")

    started = time.monotonic()
    assert commands.cmd_dev(voice=False) == 1
    # Well under the 30s startup timeout: a crashed API is noticed immediately.
    assert time.monotonic() - started < 10
    assert not (tmp_path / "ui.pid").exists()


def test_start_runs_the_api_with_voice_and_returns_its_exit_code(fake_runtime, monkeypatch):
    monkeypatch.setenv("FAKE_LIFETIME", "0")
    monkeypatch.setenv("FAKE_EXIT_CODE", "5")

    assert commands.cmd_start() == 5
    assert fake_runtime.api_launch()["NO_VOICE"] is None
