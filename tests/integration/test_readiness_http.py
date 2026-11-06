"""launcher.readiness against a real HTTP server on localhost."""

from __future__ import annotations

import http.server
import threading

import pytest

from launcher import readiness

pytestmark = pytest.mark.integration


class _StatusHandler(http.server.BaseHTTPRequestHandler):
    status = 200

    def do_GET(self):
        self.send_response(self.status)
        self.end_headers()

    def log_message(self, *args):  # keep test output quiet
        pass


def _serve(port: int, status: int) -> http.server.HTTPServer:
    handler = type("Handler", (_StatusHandler,), {"status": status})
    server = http.server.HTTPServer(("127.0.0.1", port), handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    return server


@pytest.fixture()
def server_factory():
    servers = []

    def start(port: int, status: int = 200):
        server = _serve(port, status)
        servers.append(server)
        return server

    yield start
    for server in servers:
        server.shutdown()
        server.server_close()


def test_is_serving_true_for_a_live_server(server_factory, free_port):
    port = free_port()
    server_factory(port)
    assert readiness.is_serving(f"http://127.0.0.1:{port}/api/v1/health")


def test_is_serving_false_for_an_error_status(server_factory, free_port):
    port = free_port()
    server_factory(port, status=503)
    assert not readiness.is_serving(f"http://127.0.0.1:{port}/")


def test_is_serving_false_when_nothing_is_listening(free_port):
    assert not readiness.is_serving(f"http://127.0.0.1:{free_port()}/", timeout=0.5)


def test_wait_until_serving_picks_up_a_server_that_starts_late(server_factory, free_port):
    port = free_port()
    timer = threading.Timer(0.3, server_factory, args=(port,))
    timer.start()
    try:
        assert readiness.wait_until_serving(f"http://127.0.0.1:{port}/", timeout=10, interval=0.05)
    finally:
        timer.join()


def test_wait_until_serving_gives_up_after_the_timeout(free_port):
    assert not readiness.wait_until_serving(f"http://127.0.0.1:{free_port()}/", timeout=0.3, interval=0.05)
