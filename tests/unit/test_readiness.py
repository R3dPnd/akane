"""Unit tests for launcher.readiness — polling a URL until it serves 200."""

from __future__ import annotations

import urllib.error

import pytest

from launcher import readiness


class _Response:
    def __init__(self, status: int):
        self.status = status

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False


@pytest.fixture()
def no_sleep(monkeypatch):
    monkeypatch.setattr(readiness.time, "sleep", lambda _seconds: None)


def _urlopen_returning(*outcomes):
    """Fake urlopen that yields each outcome in turn (a status code or an exception)."""
    calls = []
    remaining = list(outcomes)

    def fake_urlopen(url, timeout):
        calls.append(url)
        outcome = remaining.pop(0) if len(remaining) > 1 else remaining[0]
        if isinstance(outcome, Exception):
            raise outcome
        return _Response(outcome)

    return fake_urlopen, calls


class TestIsServing:
    def test_true_on_http_200(self, monkeypatch):
        fake, _ = _urlopen_returning(200)
        monkeypatch.setattr(readiness.urllib.request, "urlopen", fake)
        assert readiness.is_serving("http://x") is True

    def test_false_on_non_200(self, monkeypatch):
        fake, _ = _urlopen_returning(204)
        monkeypatch.setattr(readiness.urllib.request, "urlopen", fake)
        assert readiness.is_serving("http://x") is False

    @pytest.mark.parametrize(
        "error",
        [urllib.error.URLError("refused"), ConnectionResetError(), TimeoutError()],
    )
    def test_false_when_connection_fails(self, monkeypatch, error):
        fake, _ = _urlopen_returning(error)
        monkeypatch.setattr(readiness.urllib.request, "urlopen", fake)
        assert readiness.is_serving("http://x") is False


class TestWaitUntilServing:
    def test_returns_true_once_the_url_comes_up(self, monkeypatch, no_sleep):
        fake, calls = _urlopen_returning(urllib.error.URLError("down"), urllib.error.URLError("down"), 200)
        monkeypatch.setattr(readiness.urllib.request, "urlopen", fake)

        assert readiness.wait_until_serving("http://x", timeout=10) is True
        assert len(calls) == 3

    def test_returns_false_after_timeout(self, monkeypatch, no_sleep):
        clock = iter(range(0, 1000))
        monkeypatch.setattr(readiness.time, "monotonic", lambda: next(clock))
        fake, _ = _urlopen_returning(urllib.error.URLError("down"))
        monkeypatch.setattr(readiness.urllib.request, "urlopen", fake)

        assert readiness.wait_until_serving("http://x", timeout=5) is False

    def test_stops_early_when_should_abort_says_so(self, monkeypatch, no_sleep):
        fake, calls = _urlopen_returning(urllib.error.URLError("down"))
        monkeypatch.setattr(readiness.urllib.request, "urlopen", fake)

        assert readiness.wait_until_serving("http://x", timeout=1000, should_abort=lambda: True) is False
        assert calls == []
