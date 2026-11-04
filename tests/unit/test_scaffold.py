"""The repo's own layout: the runtime submodule and what stays out of git."""

from __future__ import annotations

from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]


def test_runtime_submodule_is_the_persona_agnostic_runtime():
    from launcher.paths import RUNTIME_DIR

    assert (RUNTIME_DIR / "shared" / "persona.py").is_file()


def test_gitignore_keeps_machine_files_out():
    text = (REPO_ROOT / ".gitignore").read_text()
    for entry in ["config.local.yaml", ".venv/", "models/*.onnx", "models/piper/", "training/", ".superpowers/"]:
        assert entry in text
