"""Unit tests for launcher.supervisor — owning child processes and shutting
them all down together."""

from __future__ import annotations

import signal
import threading

import pytest

from launcher.supervisor import Supervisor


@pytest.fixture()
def supervisor():
    return Supervisor(poll_interval=0.001, grace_period=0.01)


class TestWait:
    def test_returns_when_an_essential_process_exits_and_stops_the_rest(self, supervisor, fake_process_factory):
        api = fake_process_factory("api")
        ui = fake_process_factory("ui", returncode=3)
        supervisor.add(api)
        supervisor.add(ui)

        assert supervisor.wait() == 3
        assert api.terminated
        assert not ui.terminated  # already exited, nothing to terminate

    def test_non_essential_exit_does_not_end_the_session(self, supervisor, fake_process_factory):
        window = fake_process_factory("electron-window", returncode=0)
        api = fake_process_factory("api")
        supervisor.add(api)
        supervisor.add(window, essential=False)

        # Make the API exit a few polls later, from another thread.
        timer = threading.Timer(0.05, lambda: setattr(api, "returncode", 1))
        timer.start()
        try:
            assert supervisor.wait() == 1
        finally:
            timer.cancel()

    def test_wait_with_no_essential_processes_returns_immediately(self, supervisor):
        assert supervisor.wait() == 0


class TestShutdown:
    def test_terminates_every_running_process(self, supervisor, fake_process_factory):
        procs = [fake_process_factory(n) for n in ("api", "ui", "window")]
        for p in procs:
            supervisor.add(p)

        supervisor.shutdown()

        assert all(p.terminated for p in procs)
        assert not any(p.killed for p in procs)

    def test_force_kills_processes_that_ignore_terminate(self, supervisor, fake_process_factory):
        stubborn = fake_process_factory("stubborn", exit_on_terminate=False)
        supervisor.add(stubborn)

        supervisor.shutdown()

        assert stubborn.terminated and stubborn.killed

    def test_is_idempotent(self, supervisor, fake_process_factory):
        api = fake_process_factory("api")
        supervisor.add(api)
        supervisor.shutdown()
        supervisor.shutdown()
        assert api.returncode == -15

    def test_process_added_after_shutdown_is_stopped_immediately(self, supervisor, fake_process_factory):
        # The Electron window is spawned from a background thread; if Ctrl+C
        # lands first, the late arrival must not be orphaned.
        supervisor.shutdown()
        late = fake_process_factory("late-window")
        supervisor.add(late, essential=False)
        assert late.terminated

    def test_tolerates_a_process_that_exits_before_terminate_lands(self, supervisor, fake_process_factory):
        racer = fake_process_factory("racer")

        def vanish():
            raise ProcessLookupError

        racer.terminate = vanish
        supervisor.add(racer)
        supervisor.shutdown()  # must not raise
        assert not racer.killed


class TestSignalHandlers:
    def test_handler_shuts_down_and_exits_cleanly(self, supervisor, fake_process_factory, monkeypatch):
        installed = {}
        monkeypatch.setattr(signal, "signal", lambda sig, handler: installed.__setitem__(sig, handler))
        api = fake_process_factory("api")
        supervisor.add(api)

        supervisor.install_signal_handlers()

        assert signal.SIGINT in installed
        with pytest.raises(SystemExit) as exc_info:
            installed[signal.SIGINT](signal.SIGINT, None)
        assert exc_info.value.code == 0
        assert api.terminated
