"""The repo's non-Python assets: setup scripts, wake-word phrases, router Modelfile."""

from __future__ import annotations

import subprocess
import sys

import pytest

from launcher.paths import REPO_ROOT, RUNTIME_DIR

SCRIPTS = ["setup.sh", "build_router.sh", "train_wakeword.sh"]
ALBA_URL = "https://huggingface.co/rhasspy/piper-voices/resolve/main/en/en_GB/alba/medium/"


@pytest.mark.parametrize("name", SCRIPTS)
def test_script_is_valid_bash(name):
    script = REPO_ROOT / "scripts" / name
    assert script.is_file()
    result = subprocess.run(["bash", "-n", str(script)], capture_output=True, text=True)
    assert result.returncode == 0, result.stderr


@pytest.mark.parametrize("name", SCRIPTS)
def test_script_is_executable(name):
    assert (REPO_ROOT / "scripts" / name).stat().st_mode & 0o111


def test_wake_phrases_are_uh_kane_and_disjoint():
    sys.path.insert(0, str(RUNTIME_DIR / "scripts" / "wakeword"))
    try:
        from wakeword_args import load_phrases
    finally:
        sys.path.pop(0)

    positive, adversarial = load_phrases(REPO_ROOT / "wakeword" / "phrases.yaml")
    assert positive and adversarial
    assert not set(positive) & set(adversarial)
    assert all("kane" in p.lower() for p in positive)
    assert "okay Dann" in adversarial  # the old persona must not wake Akane


def test_router_modelfile():
    text = (REPO_ROOT / "models" / "akane-router.Modelfile").read_text()
    # qwen3:8b, chosen by the user after qwen2.5:7b proved unreliable at
    # calling tools (it would claim "I've set a reminder" without calling one).
    assert "FROM qwen3:8b" in text
    assert "PARAMETER num_ctx 8192" in text
    assert "Akane" in text


def test_modelfile_is_tracked_despite_models_being_ignored():
    result = subprocess.run(["git", "check-ignore", "models/akane-router.Modelfile"], cwd=REPO_ROOT)
    assert result.returncode == 1  # 1 = not ignored


def test_setup_downloads_alba_and_never_uses_an_api_key():
    text = (REPO_ROOT / "scripts" / "setup.sh").read_text()
    assert ALBA_URL in text
    assert "en_GB-alba-medium" in text
    assert "ANTHROPIC" not in text
    assert "ollama pull qwen3:8b" in text


def test_build_router_uses_the_runtime_script_and_akane_modelfile():
    text = (REPO_ROOT / "scripts" / "build_router.sh").read_text()
    assert "runtime/scripts/wakeword/build_router_model.sh" in text
    assert "akane-router models/akane-router.Modelfile" in text


def test_train_wakeword_writes_ok_akane():
    text = (REPO_ROOT / "scripts" / "train_wakeword.sh").read_text()
    assert "wakeword/phrases.yaml" in text
    assert "models/ok_akane.onnx" in text
    assert "record_wakeword_samples.py" in text


def test_setup_installs_the_akane_command():
    text = (REPO_ROOT / "scripts" / "setup.sh").read_text()
    assert 'ln -sf "$REPO/akane.py" "$HOME/.local/bin/akane"' in text
