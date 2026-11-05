"""Akane's config.yaml against the runtime submodule it drives.

These catch drift between this repo and runtime/: a server module renamed
upstream, a relative path that no longer resolves from runtime/ (where the
API/voice process runs), tool names that collide between servers, or config
the runtime's own loaders reject.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest
import yaml

from launcher.paths import CONFIG_PATH, REPO_ROOT, RUNTIME_DIR

pytestmark = pytest.mark.integration

LOCAL_EXAMPLE = REPO_ROOT / "config.local.example.yaml"


@pytest.fixture(scope="module")
def runtime_on_path():
    """Make the runtime's packages (voice, shared, integrations) importable."""
    sys.path.insert(0, str(RUNTIME_DIR))
    yield
    sys.path.remove(str(RUNTIME_DIR))


@pytest.fixture(scope="module")
def config(runtime_on_path):
    # The tracked file alone: a developer's config.local.yaml must not change
    # what these tests see (test_runtime_loader_accepts_the_config covers the
    # runtime's own loader).
    return yaml.safe_load(CONFIG_PATH.read_text())


def _servers(config):
    return config["mcp"]["servers"]


def _python_module_servers(config):
    return [s for s in _servers(config) if s["args"][:1] == ["-m"]]


def _always_on(config):
    return [s for s in _servers(config) if s.get("always_on")]


def _enabled_agents(config):
    return [a for a in config["agents"] if a.get("enabled", True)]


def test_persona_block(config):
    from shared.persona import persona_from_config

    p = persona_from_config(config)
    assert (p.name, p.wake_phrase) == ("Akane", "ok Akane")
    assert p.data_dir == Path("~/.akane").expanduser()
    assert (p.api_port, p.ui_port) == (8000, 3000)
    assert p.theme == "rose"


def test_runtime_loader_accepts_the_config(runtime_on_path):
    from voice.config import load_config

    loaded = load_config(CONFIG_PATH)
    for section in ("persona", "audio", "wake_word", "stt", "ollama", "tts", "agents", "focus_areas", "mcp"):
        assert section in loaded, f"config.yaml is missing `{section}:`"


def test_voice_and_router_choices(config):
    assert config["tts"]["voice_model"] == "../models/piper/en_GB-alba-medium"
    assert config["wake_word"]["model"] == "../models/ok_akane.onnx"
    assert config["ollama"]["model"] == "akane-router"


def test_agents_compile_into_prompt(config):
    from shared.agents_config import build_routing_prompt

    section = build_routing_prompt(config["agents"])
    for name in ("local", "lookup", "apps", "reminders", "recall"):
        assert name in section
    for later in ("plan_day", "deep_think", "apply"):
        assert later not in section, f"{later} is a later phase and must stay disabled"


def test_mcp_server_names_are_unique(config):
    names = [s["name"] for s in _servers(config)]
    assert len(names) == len(set(names))


def test_always_on_tool_allowlists_are_disjoint(config):
    # pnd-mcp's notes_server and pnd-notes both define search_notes.
    seen: dict[str, str] = {}
    for server in _always_on(config):
        assert server.get("tools"), f"{server['name']} needs a tools allowlist"
        for tool in server["tools"]:
            assert tool not in seen, f"{tool} in both {seen[tool]} and {server['name']}"
            seen[tool] = server["name"]


def test_enabled_agents_only_use_always_on_tools(config):
    exposed = {t for s in _always_on(config) for t in s["tools"]}
    for agent in _enabled_agents(config):
        missing = set(agent.get("tools") or []) - exposed
        assert not missing, f"agent {agent['name']!r} routes to unexposed tools {sorted(missing)}"


def test_lock_screen_not_exposed(config):
    # No spoken confirmation exists until Phase 3, so it isn't offered at all.
    for server in _always_on(config):
        assert "lock_screen" not in server["tools"]


def test_calendar_is_deferred(config):
    (schedule,) = [s for s in _servers(config) if s["name"] == "schedule"]
    assert not schedule.get("always_on")
    for agent in _enabled_agents(config):
        assert not {"list_events", "create_event", "find_event"} & set(agent.get("tools") or [])


def test_no_absolute_paths_in_tracked_config():
    text = CONFIG_PATH.read_text()
    assert "/Users/" not in text and "~/Git" not in text


def test_python_servers_use_the_repo_root_venv_relative_to_runtime(config):
    for server in _python_module_servers(config):
        resolved = Path(os.path.normpath(RUNTIME_DIR / server["command"]))
        assert resolved.parent.parent == REPO_ROOT / ".venv", server["name"]


def test_python_server_modules_exist_in_the_runtime(config):
    for server in _python_module_servers(config):
        module_file = RUNTIME_DIR / (server["args"][1].replace(".", "/") + ".py")
        assert module_file.is_file(), f"{server['name']}: {server['args'][1]} not found in runtime/"


def test_always_on_python_tools_exist_in_their_servers(config, python_exe):
    """Each allowlisted tool must really be registered by its server — a typo or
    upstream rename otherwise only shows up mid-conversation."""
    code = (
        "import asyncio, importlib, json, sys\n"
        "server = importlib.import_module(sys.argv[1]).mcp\n"
        "print(json.dumps(sorted(t.name for t in asyncio.run(server.list_tools()))))\n"
    )
    for server in _always_on(config):
        if server["args"][:1] != ["-m"]:
            continue
        result = subprocess.run(
            [python_exe, "-c", code, server["args"][1]], cwd=RUNTIME_DIR, capture_output=True, text=True, timeout=120
        )
        assert result.returncode == 0, result.stderr
        served = set(json.loads(result.stdout.strip().splitlines()[-1]))
        missing = set(server["tools"]) - served
        assert not missing, f"{server['name']} doesn't serve {sorted(missing)}"


def test_node_servers_resolve_relative_to_runtime(config):
    # Sibling repos (pnd-notes, godot-mcp) live next to akane; skip any that
    # aren't cloned on this machine — preflight warns about those at startup.
    for server in _servers(config):
        if server["command"] != "node":
            continue
        rel = server["args"][0]
        assert not os.path.isabs(rel)
        script = (RUNTIME_DIR / rel).resolve()
        package_dir = script.parent.parent
        if not package_dir.is_dir():
            pytest.skip(f"{package_dir} not cloned here")
        assert (package_dir / "package.json").is_file(), f"{server['name']}: {package_dir} is not a node package"


def test_local_overlay_example_only_has_comments():
    assert LOCAL_EXAMPLE.is_file()
    assert yaml.safe_load(LOCAL_EXAMPLE.read_text()) is None


def test_router_temperature_is_low_enough_for_reliable_tool_calls(config):
    # Measured live (Phase 2): at 0.7 qwen2.5:7b skipped add_reminder 2 times
    # in 3 and web_search 2 in 3 — and still claimed it had acted. At 0.1:
    # reminders 9/12, web lookups 4/4.
    assert config["ollama"]["temperature"] <= 0.2


def test_typed_replies_are_spoken(config):
    # The user wants Akane to read her replies aloud while they type.
    assert config["ux"]["speak_typed_replies"] is True


def test_runtime_supports_speaking_typed_replies(runtime_on_path):
    from voice.orchestrator import Orchestrator

    assert hasattr(Orchestrator, "_speak_queued")


def test_runtime_ui_has_the_rose_theme():
    assert '[data-theme="rose"]' in (RUNTIME_DIR / "ui" / "src" / "theme.css").read_text()


def test_local_example_documents_the_user_block():
    text = LOCAL_EXAMPLE.read_text()
    assert "# user:" in text and "location:" in text


def test_runtime_folds_the_user_block_into_prompts(runtime_on_path):
    from shared.user_context import build_user_prompt

    assert "Tacoma, WA" in build_user_prompt({"location": "Tacoma, WA"})


def test_local_example_documents_job_hunt():
    text = LOCAL_EXAMPLE.read_text()
    assert "# job_hunt:" in text and "pay_floor_hourly" in text


def test_job_search_base_url_configured(config):
    assert config["job_search"]["base_url"] == "http://localhost:8080/api/v1"


ACT_DONT_OFFER = ("When the user asks to find jobs, read the morning report, or dismiss, apply to or update a lead, "
                  "call the tool immediately. Never ask \"would you like me to…?\" for these.")


def test_job_search_tools_exposed_and_routed(config):
    (server,) = [s for s in config["mcp"]["servers"] if s["name"] == "job_search"]
    assert server["always_on"] and server["env"]["PND_JOB_SEARCH_URL"] == "http://localhost:8080/api/v1"
    (agent,) = [a for a in config["agents"] if a["name"] == "jobs"]
    assert agent.get("enabled", True)
    assert set(agent["tools"]) <= set(server["tools"])
    assert {"get_morning_report", "dismiss_lead", "mark_applied", "update_application", "start_hunt"} <= set(agent["tools"])


def test_always_on_tool_count_stays_small(config):
    always_on = sum(len(s["tools"]) for s in config["mcp"]["servers"] if s.get("always_on"))
    assert always_on + 3 <= 22  # + list/enable/disable_module meta-tools


def test_prompt_says_act_dont_offer(config):
    assert " ".join(ACT_DONT_OFFER.split()) in " ".join(config["ollama"]["system_prompt"].split())
