"""Unit tests for launcher.venv — `akane` typed in any shell runs under the
repo's own .venv, whatever `python3` happens to be first on PATH."""

from __future__ import annotations

from pathlib import Path

from launcher import venv


def _call(prefix: str, venv_dir: Path, python_exists: bool = True):
    calls = []
    python = venv_dir / "bin" / "python"
    if python_exists:
        python.parent.mkdir(parents=True)
        python.write_text("")
    venv.ensure_venv(
        ["dev", "--voice"],
        script=Path("/repo/akane.py"),
        prefix=prefix,
        venv_dir=venv_dir,
        execv=lambda exe, argv: calls.append((exe, argv)),
    )
    return calls, python


def test_reexecs_under_the_venv_python_with_the_same_args(tmp_path):
    calls, python = _call("/some/other/venv", tmp_path / ".venv")
    assert calls == [(str(python), [str(python), "/repo/akane.py", "dev", "--voice"])]


def test_does_nothing_when_already_in_the_venv(tmp_path):
    venv_dir = tmp_path / ".venv"
    calls, _ = _call(str(venv_dir), venv_dir)
    assert calls == []


def test_does_nothing_without_a_venv(tmp_path):
    # Before scripts/setup.sh has run there's nothing to switch to; carry on and
    # let the missing imports explain themselves.
    calls, _ = _call("/usr", tmp_path / ".venv", python_exists=False)
    assert calls == []
