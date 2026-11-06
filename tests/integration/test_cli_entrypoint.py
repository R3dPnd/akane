"""Run `akane.py` as a real subprocess — the way users (and `akane restart`) do.

Only side-effect-free invocations are exercised here: `stop`/`restart` act on
every akane process on the machine, so they're covered in
test_discovery_processes.py with discovery narrowed to test-owned processes.
"""

from __future__ import annotations

import subprocess

import pytest

from launcher.paths import REPO_ROOT

pytestmark = pytest.mark.integration

AKANE_PY = REPO_ROOT / "akane.py"


def _run(python_exe, *args, cwd):
    return subprocess.run([python_exe, str(AKANE_PY), *args], cwd=cwd, capture_output=True, text=True, timeout=30)


def test_no_arguments_prints_usage(python_exe, tmp_path):
    # Run from an unrelated directory: akane.py must find the launcher package on its own.
    result = _run(python_exe, cwd=tmp_path)
    assert result.returncode == 0
    assert "usage: akane" in result.stdout


def test_help_documents_every_subcommand(python_exe, tmp_path):
    result = _run(python_exe, "--help", cwd=tmp_path)
    assert result.returncode == 0
    for name in ("dev", "code", "electron", "start", "stop", "restart"):
        assert name in result.stdout


def test_unknown_command_fails_with_a_usage_error(python_exe, tmp_path):
    result = _run(python_exe, "bogus", cwd=tmp_path)
    assert result.returncode == 2
    assert "invalid choice: 'bogus'" in result.stderr


def test_installed_symlink_runs_under_the_venv_from_a_foreign_python(tmp_path):
    """`akane` is a symlink in ~/.local/bin to akane.py, run by whatever
    python3 is on PATH — which may lack psutil/yaml. It must still work."""
    link = tmp_path / "akane"
    link.symlink_to(REPO_ROOT / "akane.py")
    result = subprocess.run(["/usr/bin/python3", str(link), "--help"], capture_output=True, text=True, timeout=60)
    assert result.returncode == 0, result.stderr
    assert "akane" in result.stdout
