"""Unit tests for launcher.paths — the repo/runtime layout the launcher depends on."""

from __future__ import annotations

from pathlib import Path

from launcher import paths


def test_repo_root_is_the_directory_containing_akane_py():
    assert (paths.REPO_ROOT / "akane.py").is_file()


def test_runtime_dir_is_the_submodule_under_the_repo_root():
    assert paths.RUNTIME_DIR == paths.REPO_ROOT / "runtime"


def test_ui_dir_lives_inside_the_runtime():
    assert paths.UI_DIR == paths.RUNTIME_DIR / "ui"


def test_config_path_points_at_the_persona_config():
    assert paths.CONFIG_PATH == paths.REPO_ROOT / "config.yaml"


def test_venv_executables_live_in_the_repo_root_venv():
    assert paths.VENV_UVICORN.parent == paths.VENV_BIN
    assert paths.VENV_BIN.parent == paths.REPO_ROOT / ".venv"


def test_node_tool_uses_cmd_shim_on_windows(monkeypatch):
    monkeypatch.setattr(paths, "IS_WINDOWS", True)
    assert paths.node_tool("npm") == "npm.cmd"
    assert paths.node_tool("npx") == "npx.cmd"


def test_node_tool_is_bare_name_elsewhere(monkeypatch):
    monkeypatch.setattr(paths, "IS_WINDOWS", False)
    assert paths.node_tool("npm") == "npm"


def test_ports_are_distinct():
    assert paths.API_PORT != paths.UI_PORT


def test_url_helpers():
    assert paths.api_health_url(8000) == "http://127.0.0.1:8000/api/v1/health"
    assert paths.ui_url(3000) == "http://localhost:3000"


def test_all_paths_are_absolute():
    for value in (paths.REPO_ROOT, paths.RUNTIME_DIR, paths.UI_DIR, paths.CONFIG_PATH, paths.VENV_UVICORN):
        assert isinstance(value, Path) and value.is_absolute()


def test_ports_come_from_persona_block(tmp_path, monkeypatch):
    cfg = tmp_path / "config.yaml"
    cfg.write_text("persona: {api_port: 8100, ui_port: 3100}\n")
    monkeypatch.setattr(paths, "CONFIG_PATH", cfg)
    p = paths.load_persona()
    assert (p.api_port, p.ui_port) == (8100, 3100)


def test_missing_config_falls_back_to_defaults(tmp_path, monkeypatch):
    monkeypatch.setattr(paths, "CONFIG_PATH", tmp_path / "nope.yaml")
    assert paths.load_persona().api_port == 8000


def test_persona_name_is_read_from_config(tmp_path, monkeypatch):
    cfg = tmp_path / "config.yaml"
    cfg.write_text("persona: {name: Akane}\n")
    monkeypatch.setattr(paths, "CONFIG_PATH", cfg)
    assert paths.load_persona().name == "Akane"
