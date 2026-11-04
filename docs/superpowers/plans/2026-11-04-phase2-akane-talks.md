# Phase 2 — Akane Talks Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** A runnable `akane` persona repo: say "ok Akane" (uh-KANE), hear the Alba voice, and have it open apps, do quick web lookups, take reminders and read pnd-notes, on the existing dashboard titled Akane.

**Architecture:** Mirror `dann-of-thursday`: `runtime/` is the pnd-mcp submodule (Phase 1 commit), a ported `launcher/` package that reads ports from Akane's `persona:` block, a tracked `config.yaml` that defines Akane, and a gitignored `config.local.yaml` for machine-specific bits. Every runtime process runs with `cwd=runtime/`, so every relative path in config is written relative to `runtime/` (e.g. `../models/ok_akane.onnx`).

**Tech Stack:** Python 3.11+, pytest + pytest-cov, psutil, PyYAML; pnd-mcp runtime (FastAPI, openWakeWord, faster-whisper, Ollama, Piper); Node for pnd-notes.

**Spec:** `docs/superpowers/specs/2026-10-26-akane-design.md` (§6.2, §6.4, §6.5, §6.7, §6.10, §7, §9 Phase 2). Reference implementation to port from: `~/Git/r3dpnd/dann-of-thursday` (launcher/, tests/, pyproject.toml, requirements*.txt, .gitignore).

## Global Constraints

- Persona block exactly: `name: Akane`, `wake_phrase: "ok Akane"`, `data_dir: ~/.akane`, `api_port: 8000`, `ui_port: 3000`.
- Runtime submodule: `runtime` → `https://github.com/R3dPnd/pnd-mcp.git`, pinned to `11e4b7c` (branch `persona-agnostic`). That branch is **not pushed yet**: ask the user before pushing it; until then, add the submodule from the local path and set the URL afterwards (Task 1).
- Never write to `~/.dann`, `dann-of-thursday`, or `pnd-notes`. Never modify `runtime/` from this plan; a needed runtime change is a separate pnd-mcp commit, raised with the user first.
- No absolute paths in tracked files. Machine-specific values go in `config.local.yaml` (gitignored).
- Claude only via the `claude` CLI bridge (`claude_server`); no `anthropic` SDK, no `ANTHROPIC_API_KEY`.
- TTS voice: Piper `en_GB-alba-medium`. Router: `akane-router` built `FROM qwen2.5:7b-instruct`, `num_ctx 8192`.
- Launcher coverage ≥95% (`pytest --cov=launcher`), as in Dann.
- Integration tests never talk to a real running assistant.
- **Plan decision:** `config.yaml` is tracked (it holds no secrets; Dann's was ignored only for a Picovoice key). No `config.example.yaml`. `config.local.example.yaml` is tracked; `config.local.yaml` is ignored.
- Calendar is deferred to Phase 3d: `schedule` is registered with `always_on: false` and no agent routes to it.

## Review Focus

1. **Dann is still running when `akane dev` starts** → port 8000/3000 is taken. Expect a clear error naming the port and suggesting `dann stop`, not a uvicorn traceback. Pinned in Task 3.
2. **`akane stop` must never kill Dann's processes** (both have a `runtime/` dir and a uvicorn on `app.main:app`). Discovery matches by this repo's own paths only. Pinned in Task 2.
3. **Duplicate tool names across always-on servers**: pnd-mcp `notes_server` and pnd-notes both define `search_notes`. Expect allowlists that keep them disjoint. Pinned in Task 4.
4. **Fresh Mac with no `ok_akane.onnx`, no Alba voice, or no `akane-router`**: `akane dev --voice` should say exactly what is missing and the command that fixes it. Pinned in Task 3.
5. **`pnd-notes` not cloned next to `akane`**: Akane still starts and warns that pnd-notes is unavailable. Pinned in Task 3 (preflight warning) and Task 4 (path check is relative).

---

### Task 1: Repo scaffold and runtime submodule

**Files:**
- Create: `akane.py`, `pyproject.toml`, `requirements.txt`, `requirements-dev.txt`, `.gitignore` (append to the existing one, which holds `.superpowers/`), `tests/__init__.py`, `tests/conftest.py`, `tests/unit/__init__.py`, `tests/integration/__init__.py`, `tests/unit/test_scaffold.py`
- Create: `.gitmodules` (via `git submodule add`)

**Interfaces:**
- Produces: `runtime/` importable when on `sys.path`; `akane.py` calls `launcher.cli.main(sys.argv[1:])` (launcher comes in Task 2).

- [ ] **Step 1: Add the submodule from the local clone, then point it at GitHub**

```bash
cd ~/Git/r3dpnd/akane
git -c protocol.file.allow=always submodule add ../pnd-mcp runtime
git -C runtime checkout 11e4b7c
git config -f .gitmodules submodule.runtime.url https://github.com/R3dPnd/pnd-mcp.git
git submodule sync
```

- [ ] **Step 2: Copy and adapt Dann's project files.** `pyproject.toml` is identical to Dann's. `requirements*.txt` are Dann's with the psutil comment saying `akane`. `.gitignore` is Dann's, minus the `config.yaml` and Cloudflare lines, plus `config.local.yaml`, `models/piper/`, `training/`. `akane.py` is `dann.py` with every "dann"/"Dann of Thursday" changed to "akane"/"Akane".

- [ ] **Step 3: Write `tests/unit/test_scaffold.py`**

```python
def test_runtime_submodule_is_the_persona_agnostic_runtime():
    from launcher.paths import RUNTIME_DIR  # will fail until Task 2; keep the import local
    assert (RUNTIME_DIR / "shared" / "persona.py").is_file()

def test_gitignore_keeps_machine_files_out():
    text = (REPO_ROOT / ".gitignore").read_text()
    for entry in ["config.local.yaml", ".venv/", "models/*.onnx", "models/piper/", "training/", ".superpowers/"]:
        assert entry in text
```

(`REPO_ROOT = Path(__file__).resolve().parents[2]`.) The first test fails until Task 2 exists. That's expected, so mark it `xfail(strict=True)` with reason "launcher arrives in Task 2", and Task 2 removes the mark.

- [ ] **Step 4: Create the venv and install**

Run: `python3 -m venv .venv && .venv/bin/pip install -r requirements-dev.txt`
Expected: installs cleanly (it pulls the runtime's requirements).

- [ ] **Step 5: Run** `.venv/bin/pytest tests/unit/test_scaffold.py -v`. Expected: 1 passed, 1 xfailed.

- [ ] **Step 6: Commit** with the message "Scaffold akane: runtime submodule (pnd-mcp persona-agnostic), project files".

---

### Task 2: Port the launcher, persona-driven

**Files:**
- Create: `launcher/{__init__,cli,commands,discovery,paths,processes,readiness,supervisor}.py`, ported from `dann-of-thursday/launcher/`
- Create: `tests/unit/test_{cli,commands,discovery,paths,processes,readiness,supervisor}.py` and `tests/integration/{conftest,test_cli_entrypoint,test_commands_end_to_end,test_discovery_processes,test_readiness_http,test_supervisor_processes}.py`, ported from Dann's
- Modify: `tests/unit/test_scaffold.py` (drop the xfail)

**Interfaces:**
- Produces in `launcher/paths.py`:
  - `CONFIG_PATH = REPO_ROOT / "config.yaml"`, `MODELS_DIR = REPO_ROOT / "models"`
  - `def load_persona() -> "Persona"`: imports `shared.persona.persona_from_config` and `voice.config.load_config` from `RUNTIME_DIR` (inserting it on `sys.path` if needed) and returns `persona_from_config(load_config(CONFIG_PATH))`. It returns the defaults if `config.yaml` is missing.
  - `API_PORT`, `UI_PORT` become `load_persona().api_port` / `.ui_port`, read once at import.
- Produces in `launcher/processes.py`: `build_api_env(voice, base_env=None) -> dict[str, str]` sets `PND_CONFIG_PATH`, `PND_API_PORT`, `PND_UI_PORT`, `PND_PERSONA_NAME` (and no `DANN_*` names). The UI/Electron env gets the same three `PND_*` port/name vars.
- Produces in `launcher/discovery.py`: `LAUNCHER_SCRIPT_NAMES = {"akane.py", "akane"}`, and `is_akane_process(cmdline, cwd) -> bool` / `find_akane_processes(...)` (renamed from `is_dann_process`/`find_dann_processes`).
- All user-facing strings, the prefixes and `prog="akane"` say Akane. `_INFO` etc. print `[akane]`.

- [ ] **Step 1: Port the tests first**, renaming dann→akane. Add these new tests:

```python
# tests/unit/test_processes.py
def test_api_env_points_runtime_at_akane_config_and_ports():
    env = processes.build_api_env(voice=True, base_env={"DANN_CONFIG_PATH": "/x", "NO_VOICE": "1"})
    assert env["PND_CONFIG_PATH"] == str(paths.CONFIG_PATH)
    assert env["PND_API_PORT"] == str(paths.API_PORT)
    assert env["PND_UI_PORT"] == str(paths.UI_PORT)
    assert env["PND_PERSONA_NAME"] == "Akane"
    assert "NO_VOICE" not in env

# tests/unit/test_paths.py
def test_ports_come_from_persona_block(tmp_path, monkeypatch):
    cfg = tmp_path / "config.yaml"; cfg.write_text("persona: {api_port: 8100, ui_port: 3100}\n")
    monkeypatch.setattr(paths, "CONFIG_PATH", cfg)
    p = paths.load_persona()
    assert (p.api_port, p.ui_port) == (8100, 3100)

def test_missing_config_falls_back_to_defaults(tmp_path, monkeypatch):
    monkeypatch.setattr(paths, "CONFIG_PATH", tmp_path / "nope.yaml")
    assert paths.load_persona().api_port == 8000

# tests/unit/test_discovery.py  (Review Focus 2)
def test_dann_processes_are_not_akane():
    dann_runtime = "/Users/x/Git/r3dpnd/dann-of-thursday/runtime"
    assert not discovery.is_akane_process([".venv/bin/python", "dann.py", "dev"], "/Users/x/Git/r3dpnd/dann-of-thursday")
    assert not discovery.is_akane_process(["uvicorn", "app.main:app"], dann_runtime)
    assert discovery.is_akane_process(["uvicorn", "app.main:app"], str(paths.RUNTIME_DIR))
```

- [ ] **Step 2: Run** `.venv/bin/pytest tests -v`. Expected: FAIL (`launcher` doesn't exist).

- [ ] **Step 3: Port `launcher/`** from Dann, with the interface changes above. Docstrings are updated to say Akane. Logic otherwise stays unchanged.

- [ ] **Step 4: Run** `.venv/bin/pytest tests --cov=launcher --cov-report=term-missing`. Expected: all pass, launcher coverage ≥95%.

- [ ] **Step 5: Commit** with the message "Port the launcher from dann-of-thursday; ports and name come from Akane's persona block".

---

### Task 3: Preflight checks before launch

**Files:**
- Create: `launcher/preflight.py`, `tests/unit/test_preflight.py`
- Modify: `launcher/commands.py`, so `dev`, `electron` and `start` run preflight first

**Interfaces:**
- Consumes: `paths.API_PORT`, `paths.UI_PORT`, `paths.CONFIG_PATH`, `paths.RUNTIME_DIR`
- Produces:
  - `@dataclass(frozen=True) class Problem: level: Literal["error", "warning"]; message: str; fix: str`
  - `def check(voice: bool, *, config: dict, port_in_use: Callable[[int], bool], ollama_models: Callable[[], list[str] | None]) -> list[Problem]`
  - `def report(problems: list[Problem]) -> bool`: prints each as `[akane] error|warning: <message> — fix: <fix>`, and returns `False` if any error.
  - `commands` calls `check(...)` with the real probes (a socket bind on 127.0.0.1, and `ollama list` parsed, returning `None` when ollama isn't on PATH). It exits 1 if `report` returns False.

Paths in `config` are resolved against `RUNTIME_DIR`, matching how the runtime resolves them.

| Condition | Level | Message must contain | Fix must contain |
|---|---|---|---|
| API or UI port in use | error | the port number | `dann stop` |
| `voice` and `wake_word.model` file missing | error | `ok_akane.onnx` | `scripts/train_wakeword.sh` |
| `voice` and Piper `tts.voice_model` `.onnx` missing | error | `en_GB-alba-medium` | `scripts/setup.sh` |
| `ollama.model` not in `ollama list` | warning | `akane-router` | `scripts/build_router.sh` |
| ollama not installed (`None`) | warning | `ollama` | `brew install ollama` |
| any `mcp.servers[].args` path ending `.mjs`/`.js` missing | warning | server name | `git clone` |

- [ ] **Step 1: Write the tests.** One test per table row, each asserting `level`, and asserting the "must contain" strings with `in`. Add `test_clean_machine_has_no_problems` (all present → `[]`) and `test_voice_checks_skipped_without_voice` (missing wake model, `voice=False` → no error). Add `test_report_returns_false_on_error_true_on_warnings_only`. Build configs with `tmp_path` files and monkeypatch `paths.RUNTIME_DIR` to a `tmp_path` subdir.
- [ ] **Step 2: Run** `.venv/bin/pytest tests/unit/test_preflight.py -v`. Expected: FAIL (module missing).
- [ ] **Step 3: Implement `launcher/preflight.py`** and wire it into `commands`. Update `test_commands.py` so the existing command tests stub `preflight.check` to return `[]`, and add one test where it returns an error and the command returns 1 without spawning anything.
- [ ] **Step 4: Run** `.venv/bin/pytest tests --cov=launcher`. Expected: pass, coverage ≥95%.
- [ ] **Step 5: Commit** with the message "Preflight: clear errors for busy ports and missing voice/wake/router models".

---

### Task 4: Akane's config

**Files:**
- Create: `config.yaml`, `config.local.example.yaml`, `tests/integration/test_persona_config.py` (adapted from Dann's)

**Interfaces:**
- Consumes: `launcher.paths.CONFIG_PATH`, `RUNTIME_DIR`; runtime `voice.config.load_config`, `shared.persona.persona_from_config`, `shared.agents_config`
- Produces: the config that every later phase extends.

**`config.yaml` must contain:**
- The `persona:` block from Global Constraints.
- `wake_word`: `engine: openwakeword`, `model: ../models/ok_akane.onnx`, and Dann's threshold/debounce/cooldown.
- `audio`, `stt`, `ux`: Dann's values.
- `ollama`: `model: akane-router`, `keep_alive: 30m`, `temperature: 0.7`, `max_tokens: 80`, plus a `system_prompt`. The prompt is Dann's routing rules minus the Dann/claude-terminal examples, plus the Akane persona from spec §6.2: warm, concise, 1–2 spoken sentences, says when and where something was saved. It also says to use `lookup` (web_search) for anything current or factual it isn't sure of, and that it can't add calendar events yet.
- `tts`: `engine: piper`, `voice_model: ../models/piper/en_GB-alba-medium`, `speed: 1.0`.
- `agents:` (enabled): `local`; `lookup` (tools `[web_search]`); `apps` (`[open_app, get_volume, set_volume]`); `reminders` (`[add_reminder, list_reminders]`); `recall` (`[list_areas, search_notes, get_note]`, described as the user's curated pnd-notes knowledge base). Disabled, `enabled: false`: `plan_day`, `plan`, `research`, `think`, `deep_think`, `apply`, `claude_code`, `devteam`, `godot`, `gardening`, `bjj`, each with a one-line description and a comment naming the phase that enables it.
- `mcp.servers`:

| name | command / args | always_on | tools allowlist |
|---|---|---|---|
| claude | `../.venv/bin/python -m integrations.servers.claude_server` | true | `[web_search]` |
| reminders | `… notes_server` | true | `[add_reminder, list_reminders]` |
| system | `… system_server` | true | `[open_app, get_volume, set_volume]` (no `lock_screen` until Phase 3) |
| pnd_notes | `node ../../pnd-notes/server/pnd-notes.mjs` | true | `[list_areas, search_notes, get_note]` |
| schedule | `… schedule_server` | false | — (Phase 3d) |
| projects | `… claude_code_server` | false | — |
| devteam, gardening, bjj | as Dann | false | — |
| godot | `node ../../godot-mcp/server/build/index.js` | false | Dann's allowlist + follow_up |

`config.local.example.yaml` holds commented examples only: `ollama.model` for a bigger Mac, `stt.model_size`, `audio.input_device`/`output_device`, and a note that a server's `env:` mapping is passed to it (`integrations/client.py` merges `cfg["env"]` into the server env), e.g. `PND_NOTES_DIR` for a pnd-notes clone elsewhere. Because local list values replace the whole base list, the note says to copy the full `mcp.servers` list if overriding it. MCPManager already logs and skips an always-on server that fails to start, so a missing pnd-notes doesn't block startup.

- [ ] **Step 1: Write the tests** (all `pytestmark = pytest.mark.integration`, loading `CONFIG_PATH` via the runtime's `load_config`):

```python
def test_persona_block(config):
    p = persona_from_config(config)
    assert (p.name, p.wake_phrase, str(p.data_dir)) == ("Akane", "ok Akane", str(Path("~/.akane").expanduser()))

def test_every_python_server_module_exists_in_runtime(config): ...      # as Dann's test
def test_relative_paths_resolve_from_runtime(config): ...               # command paths, wake model dir, voice dir parent exist relative to RUNTIME_DIR; pnd-notes/godot paths skipped if the sibling repo is absent
def test_always_on_tool_allowlists_are_disjoint(config):                # Review Focus 3
    seen = {}
    for s in config["mcp"]["servers"]:
        if s.get("always_on"):
            assert s.get("tools"), f"{s['name']} needs a tools allowlist"
            for t in s["tools"]:
                assert t not in seen, f"{t} in both {seen[t]} and {s['name']}"
                seen[t] = s["name"]
def test_enabled_agents_only_use_always_on_tools(config): ...           # every tool of an enabled agent is in some always-on allowlist
def test_lock_screen_not_exposed(config): ...                           # not in any allowlist
def test_no_absolute_paths_in_tracked_config():
    assert "/Users/" not in CONFIG_PATH.read_text()
def test_agents_compile_into_prompt(config):
    from shared.agents_config import build_routing_prompt
    section = build_routing_prompt(config["agents"])
    assert "lookup" in section and "plan_day" not in section
def test_local_overlay_example_is_valid_yaml_and_all_comments_or_empty(): ...
```

- [ ] **Step 2: Run** `.venv/bin/pytest tests/integration/test_persona_config.py -v`. Expected: FAIL (no config).
- [ ] **Step 3: Write `config.yaml` and `config.local.example.yaml`** per the spec above.
- [ ] **Step 4: Run** `.venv/bin/pytest tests -v`. Expected: all pass.
- [ ] **Step 5: Commit** with the message "Akane config: persona, routing prompt, Phase 2 agents, tool allowlists".

---

### Task 5: Voice, router model and setup script

**Files:**
- Create: `models/akane-router.Modelfile`, `wakeword/phrases.yaml`, `scripts/setup.sh`, `scripts/build_router.sh`, `scripts/train_wakeword.sh`, `tests/unit/test_assets.py`

**Interfaces:**
- Consumes: runtime `scripts/wakeword/{generate_wakeword_samples,train_wakeword}.py` (`--phrases-file`, `--out-dir`, `--voice-model`, `--out-model`, `--clips-dir`), `scripts/wakeword/build_router_model.sh [name] [modelfile]`, `scripts/wakeword/wakeword_args.load_phrases`.
- Produces the fix commands that preflight (Task 3) names: `scripts/setup.sh`, `scripts/build_router.sh`, `scripts/train_wakeword.sh`.

Contents:
- **`akane-router.Modelfile`**: `FROM qwen2.5:7b-instruct`, `PARAMETER num_ctx 8192`, `top_p 0.8`, `repeat_penalty 1.1`, `num_predict 200`, and a short fallback `SYSTEM` naming Akane (same role as Dann's file and comments).
- **`phrases.yaml`**:
  - `positive`: `okay uh-kane`, `ok uh-kane`, `okay a-kane`, `ok akane`, `okay akane`, `ok uh kane`.
  - `adversarial`: `okay cane`, `ok jane`, `okay again`, `ok a game`, `okay Dann`, `hey Kane`, `ok come in`, `okay okay`, `ok google`, `hey jarvis`, `alexa`, `ok thanks`.
- **`build_router.sh`**: runs `runtime/scripts/wakeword/build_router_model.sh akane-router models/akane-router.Modelfile` from the repo root.
- **`train_wakeword.sh`**: generates clips into `training/` using `phrases.yaml` and the Alba voice, then trains to `models/ok_akane.onnx`. Prints how to add real recordings with `runtime/scripts/wakeword/record_wakeword_samples.py` for better accuracy.
- **`setup.sh`** (idempotent, `set -euo pipefail`):
  1. `git submodule update --init`
  2. create `.venv` and install `requirements-dev.txt`
  3. `npm ci` in `runtime/ui`
  4. check `ollama`, then `ollama pull qwen2.5:7b-instruct` and `build_router.sh`
  5. download `en_GB-alba-medium.onnx` + `.onnx.json` from `https://huggingface.co/rhasspy/piper-voices/resolve/main/en/en_GB/alba/medium/` into `models/piper/` if absent
  6. `npm ci` in `../pnd-notes` if present, else warn
  7. copy `config.local.example.yaml` to `config.local.yaml` if absent
  8. if `models/ok_akane.onnx` is absent, say: copy it from the old machine, or run `scripts/train_wakeword.sh`
  9. `mkdir -p ~/.akane`

Tests in `test_assets.py`:
- `bash -n` passes on each script.
- `load_phrases(phrases.yaml)` returns non-empty lists with no overlap, and every positive contains "kane".
- The Modelfile has `FROM qwen2.5:7b-instruct` and `num_ctx 8192`.
- `setup.sh` contains the exact Alba URL path and never `ANTHROPIC`.

- [ ] **Step 1: Write `tests/unit/test_assets.py`** with the tests above.
- [ ] **Step 2: Run it.** Expected: FAIL (files missing).
- [ ] **Step 3: Write the files.**
- [ ] **Step 4: Run** `.venv/bin/pytest tests -v`. Expected: all pass.
- [ ] **Step 5: Run `scripts/setup.sh` for real**, then `scripts/train_wakeword.sh`. Expected: `models/piper/en_GB-alba-medium.onnx`, `models/ok_akane.onnx`, `akane-router` in `ollama list`, and `~/.akane/` all exist.
- [ ] **Step 6: Commit** with the message "Akane voice and models: Alba TTS, ok-Akane wake word training, akane-router, setup script".

---

### Task 6: Docs and a live run with the user

**Files:**
- Create: `CLAUDE.md` (how to run, test, where config lives, the `cwd=runtime/` path rule, what not to touch), `README.md` (what Akane is, setup on a new Mac, commands, phase status)
- Modify: `docs/superpowers/specs/2026-10-26-akane-design.md` §9: mark Phase 2 done only after Step 2 passes

- [ ] **Step 1: Write the docs.**
- [ ] **Step 2: Live check with the user.** Stop Dann first (`dann stop`). Run `.venv/bin/python akane.py dev --voice` and ask the user to say each of these:

| Say | Expect |
|---|---|
| "ok Akane" (uh-KANE) | listening chime; UI shows "Listening for 'ok Akane'"; window title Akane |
| "open Spotify" | Spotify opens; reply in the Alba voice |
| "set the volume to 30" | volume changes |
| "what time does Costco close today" | spoken answer after a short pause (web_search) |
| "remind me to call the dentist tomorrow" | reminder saved in `~/.akane/notes.json` |
| "what do my notes say about <a real pnd-notes topic>" | answer drawn from pnd-notes |
| "ok Dann" / "okay again" | no wake |

Record what fails. Fix it in this repo, or raise it with the user if the fix belongs in the runtime.
- [ ] **Step 3: Run** `.venv/bin/pytest tests --cov=launcher`. Expected: all pass, ≥95%.
- [ ] **Step 4: Commit** with the message "Akane docs; Phase 2 verified live". Ask the user before pushing `akane` and pnd-mcp's `persona-agnostic` branch.
