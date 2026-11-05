"""Unit tests for launcher.cli — argument parsing and dispatch to commands."""

from __future__ import annotations

import pytest

from launcher import cli, commands


@pytest.fixture()
def recorded(monkeypatch):
    """Replace every command with a recorder that returns a distinctive code."""
    calls = []

    def recorder(name, code):
        def fake(*args, **kwargs):
            calls.append((name, args, kwargs))
            return code

        return fake

    monkeypatch.setattr(commands, "cmd_dev", recorder("dev", 10))
    monkeypatch.setattr(commands, "cmd_electron", recorder("electron", 11))
    monkeypatch.setattr(commands, "cmd_start", recorder("start", 12))
    monkeypatch.setattr(commands, "cmd_stop", recorder("stop", 13))
    monkeypatch.setattr(commands, "cmd_restart", recorder("restart", 14))
    monkeypatch.setattr(commands, "cmd_jobs_app", recorder("jobs-app", 15))
    monkeypatch.setattr(commands, "cmd_hunt", recorder("hunt", 16))
    monkeypatch.setattr(commands, "cmd_schedule", recorder("schedule", 17))
    return calls


@pytest.mark.parametrize(
    ("argv", "expected_call", "expected_code"),
    [
        (["dev"], ("dev", (), {"voice": False, "speak": False}), 10),
        (["dev", "--voice"], ("dev", (), {"voice": True, "speak": False}), 10),
        (["dev", "--speak"], ("dev", (), {"voice": False, "speak": True}), 10),
        (["code"], ("dev", (), {"voice": False, "speak": False}), 10),
        (["electron"], ("electron", (), {"voice": False, "speak": False}), 11),
        (["electron", "--voice"], ("electron", (), {"voice": True, "speak": False}), 11),
        (["electron", "--speak"], ("electron", (), {"voice": False, "speak": True}), 11),
        (["start"], ("start", (), {}), 12),
        (["stop"], ("stop", (), {}), 13),
        (["hunt"], ("hunt", (), {}), 16),
        (["schedule", "install"], ("schedule", ("install",), {}), 17),
        (["schedule", "uninstall"], ("schedule", ("uninstall",), {}), 17),
        (["schedule", "status"], ("schedule", ("status",), {}), 17),
        (["jobs-app", "install"], ("jobs-app", ("install",), {"resume": None}), 15),
        (["jobs-app", "uninstall"], ("jobs-app", ("uninstall",), {"resume": None}), 15),
        (["jobs-app", "status"], ("jobs-app", ("status",), {"resume": None}), 15),
        (["jobs-app", "load-resume", "/r/Resume.docx"], ("jobs-app", ("load-resume",), {"resume": "/r/Resume.docx"}), 15),
    ],
)
def test_dispatches_each_subcommand(recorded, argv, expected_call, expected_code):
    assert cli.main(argv) == expected_code
    assert recorded == [expected_call]


def test_restart_relaunches_as_a_fresh_akane_process(recorded, monkeypatch):
    # Relaunching in-process left the command line saying `akane restart`, so
    # a second `akane restart` found nothing restartable. The relaunch must
    # replace this process with `akane <original args>`.
    from launcher import paths

    assert cli.main(["restart"]) == 14
    ((name, _args, kwargs),) = recorded
    assert name == "restart"
    execs = []
    monkeypatch.setattr(cli.os, "execv", lambda exe, argv: execs.append((exe, argv)))
    kwargs["relaunch"](["dev", "--speak"])
    assert execs == [(cli.sys.executable, [cli.sys.executable, str(paths.REPO_ROOT / "akane.py"), "dev", "--speak"])]


def test_no_arguments_prints_usage_and_succeeds(recorded, capsys):
    assert cli.main([]) == 0
    assert "usage:" in capsys.readouterr().out
    assert recorded == []


def test_unknown_command_is_a_usage_error(recorded, capsys):
    with pytest.raises(SystemExit) as exc_info:
        cli.main(["bogus"])
    assert exc_info.value.code == 2
    assert "invalid choice" in capsys.readouterr().err
    assert recorded == []


@pytest.mark.parametrize("argv", [["start", "--voice"], ["stop", "--voice"]])
def test_voice_flag_is_rejected_where_it_means_nothing(recorded, argv):
    with pytest.raises(SystemExit):
        cli.main(argv)
    assert recorded == []


def test_help_lists_every_subcommand(capsys):
    with pytest.raises(SystemExit):
        cli.main(["--help"])
    out = capsys.readouterr().out
    for name in ("dev", "code", "electron", "start", "stop", "restart"):
        assert name in out


@pytest.mark.parametrize("command", ["dev", "electron"])
def test_voice_and_speak_are_mutually_exclusive(recorded, command):
    with pytest.raises(SystemExit):
        cli.main([command, "--voice", "--speak"])
