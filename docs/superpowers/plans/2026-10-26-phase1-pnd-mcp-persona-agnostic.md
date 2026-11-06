# Phase 1 — pnd-mcp Persona-Agnostic Runtime Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make the shared runtime (`pnd-mcp`) take its persona identity — name, wake phrase, data directory, ports — from config instead of hardcoding "Dann", split the general Claude bridge out of the coding server, and add a client chat endpoint with a context payload, while `dann-of-thursday` keeps running unchanged.

**Architecture:** A new `persona:` config block is read by one helper module (`shared/persona.py`). Every place that builds `~/.dann` asks that helper instead; MCP tool-server subprocesses get the resolved directory through an injected `PND_DATA_DIR` env var (MCP's stdio client does not inherit arbitrary env vars). Config loading gains a gitignored `config.local.yaml` overlay. All `claude` CLI invocations go through one helper that strips `ANTHROPIC_API_KEY`.

**Tech Stack:** Python 3.10+, FastAPI, `mcp==1.29.1` FastMCP servers, pytest; React/Vite/Electron UI (TypeScript).

**Spec:** `/Users/prestonharms/Git/r3dpnd/akane/docs/superpowers/specs/2026-10-26-akane-design.md` (§6.1, §6.5, §8 "Infrastructure to build now", §9 Phase 1)

**Where to work:** the standalone clone `/Users/prestonharms/Git/r3dpnd/pnd-mcp`, on a new branch `persona-agnostic` off `main` (baseline: 202 tests passing). There is no venv in that clone; use Dann's:

```bash
PY=/Users/prestonharms/Git/r3dpnd/dann-of-thursday/.venv/bin/python
cd /Users/prestonharms/Git/r3dpnd/pnd-mcp && $PY -m pytest -q
```

## Global Constraints

- **Backward compatibility is a hard requirement:** with no `persona:` block and no new env vars, every path, port, title and label behaves exactly as today (`~/.dann`, `Dann`, `ok Dann`, 8000/3000). Dann's `config.yaml` must need **no edits**.
- New env var names use the `PND_` prefix; every renamed `DANN_*` var stays readable as a fallback (`PND_*` wins when both are set).
- `mcp` stays pinned at `1.29.1`; no new Python dependencies.
- Persona defaults: `name: Dann`, `wake_phrase: "ok Dann"`, `data_dir: ~/.dann`, `api_port: 8000`, `ui_port: 3000`.
- `claude` CLI calls must never see `ANTHROPIC_API_KEY`; no code path may fall back to the billed Anthropic SDK.
- Tests never touch the real `~/.dann` or a real running assistant.
- Follow existing style: module docstrings that explain *why*, comments at the existing density, no restructuring beyond what a task names.

## Review Focus

1. `config.local.yaml` present but empty (YAML `null`) or partial → treated as `{}` / merged key-by-key, never wipes `config.yaml` sections. (Test in Task 1.)
2. `data_dir` / `PND_DATA_DIR` written with `~` → expanded to the home directory, not a literal `~` folder created in the cwd. (Test in Task 1.)
3. A server config that already has its own `env:` block (e.g. `PYTHONPATH`) keeps it when `PND_DATA_DIR` is injected; an explicit `PND_DATA_DIR` in that block wins. (Test in Task 2.)
4. `ANTHROPIC_API_KEY` set in the parent environment → absent from the env the `claude` CLI is launched with; `claude` missing from PATH → a readable tool result, not an exception. (Tests in Task 3.)
5. Client chat with empty text, missing `conversation_id`, or an oversized `context` → 400 for the first two, context truncated (not rejected) for the third. (Tests in Task 4.)

---

### Task 1: Persona config + layered config loading

**Files:**
- Modify: `voice/config.py` (resolution order + local overlay)
- Create: `shared/persona.py`
- Test: `tests/voice/test_config.py` (extend), `tests/test_persona.py` (new)

**Interfaces:**
- Produces:
  - `voice.config.load_config(path: Path | None = None) -> dict[str, Any]` — resolution: explicit arg > `PND_CONFIG_PATH` > `DANN_CONFIG_PATH` > `../config.yaml` default. After loading, if `config.local.yaml` exists **in the same directory as the resolved config**, deep-merge it over the base (dicts merge recursively; lists and scalars replace).
  - `voice.config.deep_merge(base: dict, override: dict) -> dict` (pure; returns a new dict).
  - `shared.persona.Persona` — frozen dataclass: `name: str`, `wake_phrase: str`, `data_dir: Path`, `api_port: int`, `ui_port: int`.
  - `shared.persona.persona_from_config(cfg: dict | None) -> Persona` — reads `cfg["persona"]`, fills defaults, `expanduser()` on `data_dir`.
  - `shared.persona.get_persona() -> Persona` — `persona_from_config(load_config())`, falling back to defaults if the config file is missing; cached with `functools.lru_cache` (tests call `get_persona.cache_clear()`).
  - `shared.persona.data_dir() -> Path` — `PND_DATA_DIR` env (expanded) if set, else `get_persona().data_dir`; `mkdir(parents=True, exist_ok=True)` before returning.

- [ ] **Step 1: Write failing tests**

In `tests/voice/test_config.py` add (keep the existing four tests; they must still pass unchanged):

```python
def test_pnd_config_path_wins_over_dann_config_path(self, tmp_path, monkeypatch):
    pnd = tmp_path / "pnd.yaml"; pnd.write_text("source: pnd\n")
    dann = tmp_path / "dann.yaml"; dann.write_text("source: dann\n")
    monkeypatch.setenv("PND_CONFIG_PATH", str(pnd))
    monkeypatch.setenv("DANN_CONFIG_PATH", str(dann))
    assert load_config() == {"source": "pnd"}

def test_local_overlay_deep_merges(self, tmp_path, monkeypatch):
    monkeypatch.delenv("PND_CONFIG_PATH", raising=False)
    base = tmp_path / "config.yaml"
    base.write_text("ollama:\n  model: small\n  base_url: http://x\nagents: [a, b]\n")
    (tmp_path / "config.local.yaml").write_text("ollama:\n  model: big\nagents: [c]\n")
    assert load_config(base) == {"ollama": {"model": "big", "base_url": "http://x"}, "agents": ["c"]}

def test_empty_local_overlay_is_ignored(self, tmp_path):
    base = tmp_path / "config.yaml"; base.write_text("a: 1\n")
    (tmp_path / "config.local.yaml").write_text("")
    assert load_config(base) == {"a": 1}
```

Update `test_missing_file_raises_with_a_helpful_message` to match `"PND_CONFIG_PATH"`.

`tests/test_persona.py`:

```python
def test_defaults_match_dann_when_no_persona_block():
    p = persona_from_config({})
    assert (p.name, p.wake_phrase, p.api_port, p.ui_port) == ("Dann", "ok Dann", 8000, 3000)
    assert p.data_dir == Path.home() / ".dann"

def test_persona_block_overrides_and_expands_tilde():
    p = persona_from_config({"persona": {"name": "Akane", "wake_phrase": "ok Akane",
                                         "data_dir": "~/.akane", "api_port": 8100}})
    assert p.name == "Akane" and p.api_port == 8100 and p.ui_port == 3000
    assert p.data_dir == Path.home() / ".akane"

def test_data_dir_prefers_env_and_creates_it(tmp_path, monkeypatch):
    target = tmp_path / "x" / "data"
    monkeypatch.setenv("PND_DATA_DIR", str(target))
    assert data_dir() == target and target.is_dir()

def test_data_dir_env_tilde_is_expanded(monkeypatch, tmp_path):
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setenv("PND_DATA_DIR", "~/.akane")
    assert data_dir() == tmp_path / ".akane"

def test_get_persona_falls_back_to_defaults_without_config(monkeypatch, tmp_path):
    monkeypatch.setenv("PND_CONFIG_PATH", str(tmp_path / "missing.yaml"))
    get_persona.cache_clear()
    assert get_persona().name == "Dann"
```

- [ ] **Step 2: Run to verify they fail**

Run: `$PY -m pytest tests/voice/test_config.py tests/test_persona.py -v`
Expected: FAIL — `shared.persona` import error; overlay/env tests fail.

- [ ] **Step 3: Implement `deep_merge`, the new resolution order and overlay in `voice/config.py`; implement `shared/persona.py`**

Update `load_config`'s docstring to describe the new order and the overlay. Error message names `PND_CONFIG_PATH`.

- [ ] **Step 4: Run tests to verify they pass**

Run: `$PY -m pytest -q`
Expected: all pass (202 baseline + new).

- [ ] **Step 5: Commit**

```bash
git add voice/config.py shared/persona.py tests/voice/test_config.py tests/test_persona.py
git commit -m "Add persona config block and config.local.yaml overlay"
```

---

### Task 2: Route every data path through `data_dir()` and inject it into MCP servers

**Files:**
- Modify: `integrations/servers/_store.py`, `shared/focus_areas_store.py`, `integrations/servers/schedule_server.py`, `integrations/servers/devteam_server.py`, `app/services/{chat,history,log,metrics,devteam}_service.py`, `integrations/client.py` (`_server_owner_task`), docstrings mentioning `~/.dann` in `notes_server.py`, `gardening_server.py`, `bjj_server.py`, `focus_areas_server.py`
- Modify: `tests/conftest.py`
- Test: `tests/integrations/test_mcp_client.py` (extend), `tests/app/test_data_dir_paths.py` (new)

**Interfaces:**
- Consumes: `shared.persona.data_dir()` (Task 1).
- Produces:
  - `integrations.servers._store.data_home() -> Path` (= `data_dir()`); `dann_home` kept as an alias so nothing else breaks.
  - `integrations.client.server_env(cfg: dict[str, Any]) -> dict[str, str]` — returns `{"PND_DATA_DIR": str(data_dir()), **(cfg.get("env") or {})}` (explicit server env wins). `_server_owner_task` passes this as `env=`.
  - Each service exposes its file path through a small function evaluated at call time (e.g. `_streams_file() -> Path`), replacing module-level `_DANN_DIR` constants; the log file name stays `dann.log` when the persona is Dann, otherwise `<persona name lowercased>.log`.
  - Fixture `tmp_data_dir` in `tests/conftest.py`: sets `PND_DATA_DIR` to `tmp_path` via `monkeypatch.setenv` and returns it; `tmp_dann_home` becomes an alias of it (existing tests keep their parameter name).

- [ ] **Step 1: Write failing tests**

`tests/integrations/test_mcp_client.py`:

```python
def test_server_env_injects_data_dir(tmp_path, monkeypatch):
    monkeypatch.setenv("PND_DATA_DIR", str(tmp_path))
    assert server_env({"name": "x"}) == {"PND_DATA_DIR": str(tmp_path)}

def test_server_env_keeps_existing_env_and_explicit_value_wins(tmp_path, monkeypatch):
    monkeypatch.setenv("PND_DATA_DIR", str(tmp_path))
    env = server_env({"env": {"PYTHONPATH": "/p", "PND_DATA_DIR": "/explicit"}})
    assert env == {"PYTHONPATH": "/p", "PND_DATA_DIR": "/explicit"}
```

`tests/app/test_data_dir_paths.py` — one test per service proving paths follow `PND_DATA_DIR` set *after* import:

```python
@pytest.mark.parametrize("module, fn, filename", [
    ("app.services.chat_service", "_streams_file", "work_streams.json"),
    ("app.services.history_service", "_history_file", "history.jsonl"),
    ("app.services.metrics_service", "_calls_file", "code_calls.jsonl"),
])
def test_service_paths_follow_data_dir(tmp_data_dir, module, fn, filename):
    assert getattr(importlib.import_module(module), fn)() == tmp_data_dir / filename

def test_focus_area_dir_follows_data_dir(tmp_data_dir):
    assert focus_area_dir("coding") == tmp_data_dir / "focus_areas" / "coding"
```

(Use whatever focus-area-dir function `shared/focus_areas_store.py` already exposes; match its real name.)

- [ ] **Step 2: Run to verify they fail**

Run: `$PY -m pytest tests/integrations/test_mcp_client.py tests/app/test_data_dir_paths.py -v`
Expected: FAIL — `server_env` / `_streams_file` not defined.

- [ ] **Step 3: Implement** — replace every `Path.home() / ".dann"` and `_DANN_HOME`/`_DANN_DIR` constant with call-time `data_dir()`; make `schedule_server`'s `_CREDENTIALS_FILE`/`_TOKEN_FILE` functions; add `server_env` and use it in `_server_owner_task`; update the conftest fixture; reword `~/.dann` in docstrings to "the persona data dir (`persona.data_dir`, default `~/.dann`)".

- [ ] **Step 4: Verify nothing still hardcodes the dir**

Run: `grep -rnE 'Path.home\(\) / "\.dann"|_DANN_HOME|_DANN_DIR' --include='*.py' . | grep -v '^./tests'`
Expected: no output.
Run: `$PY -m pytest -q`
Expected: all pass.

- [ ] **Step 5: Commit**

```bash
git add -A integrations shared app tests
git commit -m "Resolve all persona data paths through data_dir() and pass it to MCP servers"
```

---

### Task 3: One Claude CLI bridge, `claude_server` split, no billed fallback

**Files:**
- Create: `shared/claude_cli.py`, `integrations/servers/claude_server.py`
- Modify: `integrations/servers/claude_code_server.py` (`ask_claude`, `web_search` delegate), `integrations/servers/devteam_server.py` (use `claude_env()` for the spawned process), `app/api/v1/endpoints/prompt_builder.py` (remove SDK fallback), `claude_code_server.py`'s `DANN_API_BASE_URL` → `PND_API_BASE_URL` with fallback, default `http://localhost:{get_persona().api_port}`
- Test: `tests/test_claude_cli.py`, `tests/integrations/test_claude_server.py`

**Interfaces:**
- Produces:
  - `shared.claude_cli.claude_env() -> dict[str, str]` — copy of `os.environ` without `ANTHROPIC_API_KEY` (and without `ANTHROPIC_AUTH_TOKEN`).
  - `shared.claude_cli.ClaudeResult` — dataclass `ok: bool`, `text: str`, `error: str`.
  - `shared.claude_cli.run_claude(prompt: str, *, model: str | None = None, allowed_tools: list[str] | None = None, timeout: float = 120) -> ClaudeResult` — argv order `["claude", *(--model m), "-p", prompt, *(--allowedTools ...)]` (prompt **before** `--allowedTools`; see the existing comment about commander.js variadics). Missing binary (`shutil.which("claude") is None`), timeout, and non-zero exit all return `ok=False` with a readable `error`; never raise.
  - `integrations.servers.claude_server`: FastMCP `"claude"` with tools `ask_claude(question: str, context: str = "", depth: str = "deep") -> str` and `web_search(query: str) -> str` — same prompts, timeouts (60s / 120s) and user-facing error strings as today, implemented via `run_claude`.
  - `claude_code_server.ask_claude` / `web_search` stay registered tools (Dann's config lists them under the `projects` server) but their bodies call `claude_server`'s functions.

- [ ] **Step 1: Write failing tests** (patch `subprocess.run` and `shutil.which`; never invoke the real CLI)

```python
def test_claude_env_strips_api_keys(monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-x"); monkeypatch.setenv("ANTHROPIC_AUTH_TOKEN", "t")
    env = claude_env()
    assert "ANTHROPIC_API_KEY" not in env and "ANTHROPIC_AUTH_TOKEN" not in env and "PATH" in env

def test_run_claude_puts_prompt_before_allowed_tools_and_uses_clean_env(monkeypatch):
    # capture argv/env from a fake subprocess.run returning returncode 0, stdout "hi"
    ...
    assert argv == ["claude", "--model", "haiku", "-p", "q", "--allowedTools", "WebSearch"]
    assert "ANTHROPIC_API_KEY" not in captured_env
    assert result == ClaudeResult(ok=True, text="hi", error="")

def test_run_claude_missing_binary_returns_error(monkeypatch):
    monkeypatch.setattr("shutil.which", lambda _: None)
    r = run_claude("q")
    assert not r.ok and "claude CLI not found" in r.error

def test_run_claude_timeout_returns_error(monkeypatch): ...  # raises TimeoutExpired → ok False, "timed out" in error
```

`tests/integrations/test_claude_server.py`: `ask_claude("q", depth="fast")` calls `run_claude` with `model="haiku"`, `timeout=60`; `web_search("x")` uses `allowed_tools=["WebSearch"]`, `timeout=120`; a failed result returns `"Web search error: …"` / `"Claude returned an error: …"` exactly as today; `claude_code_server.ask_claude` returns the same as `claude_server.ask_claude` for the same patched result.

Add a test that `prompt_builder` returns its "claude CLI not found" error (HTTP 503 or whatever it already uses for that branch) when the CLI is missing **even with `ANTHROPIC_API_KEY` set** — i.e. no SDK fallback.

- [ ] **Step 2: Run to verify they fail**

Run: `$PY -m pytest tests/test_claude_cli.py tests/integrations/test_claude_server.py -v`
Expected: FAIL — modules not found.

- [ ] **Step 3: Implement** `shared/claude_cli.py`, `claude_server.py` (module docstring lists its two tools and why it's separate: a non-coding persona can enable research/reasoning without project/coding tools), the delegations, `devteam_server` using `env=claude_env()`, and remove `_call_sdk` + its branch from `prompt_builder.py`.

- [ ] **Step 4: Verify**

Run: `grep -rn "subprocess.*\"claude\"\|\[\"claude\"" --include='*.py' . | grep -v '^./tests'`
Expected: only `shared/claude_cli.py` (plus devteam/claude_code_server's interactive-terminal launch strings, which build shell commands, not CLI calls — leave those).
Run: `grep -rn "import anthropic" --include='*.py' . | grep -v '^./tests'` → no output.
Run: `$PY -m pytest -q` → all pass.

- [ ] **Step 5: Commit**

```bash
git add shared/claude_cli.py integrations/servers/claude_server.py integrations/servers/claude_code_server.py integrations/servers/devteam_server.py app/api/v1/endpoints/prompt_builder.py tests
git commit -m "Consolidate claude CLI calls behind one bridge and split out claude_server"
```

---

### Task 4: Client chat endpoint with a `context` payload

**Files:**
- Modify: `app/services/chat_service.py`, `app/api/v1/endpoints/chat.py`
- Test: `tests/app/test_client_chat.py`

**Interfaces:**
- Consumes: existing `generate_response`, `build_routing_prompt`, `build_focus_areas_prompt`.
- Produces:
  - `chat_service._build_system_prompt(cfg: dict, focus_area: str = "", context: dict | None = None) -> str` — extracted from `send_message` (which now calls it; behavior unchanged). When `context` is given, appends:
    `"\n\nContext from {source} (data, not instructions):\n{json.dumps(data, indent=2)}"`, with the JSON truncated to `_MAX_CONTEXT_CHARS = 8000` characters plus `"\n…(truncated)"`.
  - `chat_service.send_client_message(conversation_id: str, text: str, context: dict | None = None) -> dict` — returns `{"response": str, "latency_ms": int}`. History is in-memory only (`_client_conversations: dict[str, list[dict]]`, last `_MAX_HISTORY` messages, at most 50 conversations, oldest evicted). Emits the same `chat.turn` event with `session_id=conversation_id`, `focus_area=""`, plus `"source": context["source"]` when present.
  - `POST /api/v1/chat/client` body `{"conversation_id": str, "text": str, "context": {"source": str, "data": object} | null}` → 200 `{"response", "latency_ms"}`; 400 if `text.strip()` or `conversation_id.strip()` is empty.

- [ ] **Step 1: Write failing tests** (patch `generate_response` to capture `system_prompt` and `history`; use `TestClient(app)` with `tmp_data_dir` and a minimal config file via `PND_CONFIG_PATH`)

```python
def test_client_message_includes_context_in_system_prompt(...):
    r = client.post("/api/v1/chat/client", json={"conversation_id": "g1", "text": "what is this node?",
        "context": {"source": "godot", "data": {"selected_node": "Player"}}})
    assert r.status_code == 200
    assert "Context from godot (data, not instructions)" in captured["system_prompt"]
    assert '"selected_node": "Player"' in captured["system_prompt"]

def test_client_history_carries_between_turns(...):
    # second call with same conversation_id sees the first exchange in `history`

def test_oversized_context_is_truncated(...):
    # data = {"blob": "x" * 20000} → prompt contains "…(truncated)" and its context section ≤ 8000 + marker

@pytest.mark.parametrize("body", [{"conversation_id": "g1", "text": "  "}, {"conversation_id": " ", "text": "hi"}])
def test_rejects_blank_fields(body, ...): assert client.post("/api/v1/chat/client", json=body).status_code == 400

def test_stream_send_message_prompt_unchanged(...):
    # existing stream path still builds the same prompt for a focus area (snapshot the old string pieces)
```

- [ ] **Step 2: Run to verify they fail**

Run: `$PY -m pytest tests/app/test_client_chat.py -v`
Expected: FAIL — 404/405 for `/chat/client`.

- [ ] **Step 3: Implement** the extraction, `send_client_message`, and the route (blocking call via `asyncio.to_thread`, like `send_message`). Add the route to the module docstring list.

- [ ] **Step 4: Run tests**

Run: `$PY -m pytest -q` → all pass.

- [ ] **Step 5: Commit**

```bash
git add app/services/chat_service.py app/api/v1/endpoints/chat.py tests/app/test_client_chat.py
git commit -m "Add a client chat endpoint that accepts editor/app context"
```

---

### Task 5: Persona identity in the API, UI, Electron and Vite

**Files:**
- Create: `app/api/v1/endpoints/persona.py` (register it in the v1 router alongside the others)
- Modify: `app/main.py` (FastAPI `title`/`description`, root message from persona), `app/core/config.py` (`PROJECT_NAME` default stays; app uses persona name at startup), `ui/src/lib/api.ts`, `ui/src/types.ts`, `ui/src/hooks/useDannState.ts` (store `persona`), `ui/src/App.tsx` (tab label + `document.title`), `ui/src/components/VoicePanel.tsx` (idle label), `ui/electron/main.cjs`, `ui/vite.config.ts`
- Test: `tests/app/test_persona_endpoint.py`

**Interfaces:**
- Consumes: `get_persona()` (Task 1).
- Produces:
  - `GET /api/v1/persona` → `{"name": str, "wake_phrase": str}`.
  - UI type `Persona { name: string; wake_phrase: string }`, `api.getPersona()`; store field `persona: Persona | null`, defaulting to `{name: 'Dann', wake_phrase: 'ok Dann'}` until loaded.
  - Idle label: `` `Listening for '${persona.wake_phrase}'` ``. Main tab label: `persona.name.toUpperCase()` (internal tab id `'dann'` may stay). `document.title = persona.name`.
  - Electron: config path env `PND_CONFIG_PATH` (also set `DANN_CONFIG_PATH` to the same value for older runtimes), backend port `Number(process.env.PND_API_PORT || 8000)`, dev port `Number(process.env.PND_UI_PORT || 3000)`, fullscreen when `PND_FULLSCREEN === '1' || DANN_FULLSCREEN === '1'`, window title `process.env.PND_PERSONA_NAME || 'Dann of Thursday'` (the launcher sets it; the page title updates from the API anyway).
  - Vite: `server.port = Number(process.env.PND_UI_PORT || 3000)`, proxy target `` `http://127.0.0.1:${process.env.PND_API_PORT || 8000}` ``.

- [ ] **Step 1: Write failing test**

```python
def test_persona_endpoint_defaults(client_with_config_without_persona):
    assert client.get("/api/v1/persona").json() == {"name": "Dann", "wake_phrase": "ok Dann"}

def test_persona_endpoint_reads_config(client_with_config({"persona": {"name": "Akane", "wake_phrase": "ok Akane"}})):
    assert client.get("/api/v1/persona").json() == {"name": "Akane", "wake_phrase": "ok Akane"}
```

(Clear `get_persona`'s cache in the fixture.)

- [ ] **Step 2: Run to verify it fails**

Run: `$PY -m pytest tests/app/test_persona_endpoint.py -v` → FAIL (404).

- [ ] **Step 3: Implement** the endpoint and app title changes, then the UI/Electron/Vite changes.

- [ ] **Step 4: Verify**

Run: `$PY -m pytest -q` → all pass.
Run: `cd ui && npm ci && npm run build` → exits 0 (type-checks the UI changes).
Run: `grep -rn "ok Dann\|'Dann of Thursday'" ui/src ui/electron` → only the documented fallback defaults.

- [ ] **Step 5: Commit**

```bash
git add app ui tests/app/test_persona_endpoint.py
git commit -m "Show the configured persona's name and wake phrase instead of hardcoded Dann"
```

---

### Task 6: Parameterize wake-word and router-model scripts

**Files:**
- Modify: `scripts/wakeword/generate_wakeword_samples.py`, `scripts/wakeword/train_wakeword.py`, `scripts/wakeword/build_router_model.sh`
- Test: `tests/scripts/test_wakeword_args.py` (new; import the scripts' arg parsers only — no Piper/ONNX work)

**Interfaces:**
- Produces:
  - `generate_wakeword_samples.parse_args(argv: list[str] | None = None) -> argparse.Namespace` with `--phrases-file PATH` (YAML: `positive: [..]`, `adversarial: [..]`), `--out-dir PATH` (default: current behavior's `training/`), `--voice-model PATH` (default: current constant). No `--phrases-file` → today's hardcoded "ok dann" lists, unchanged. Phrases are passed to Piper as written, so a persona can spell its pronunciation phonetically (e.g. "okay uh-kane") in the file.
  - `train_wakeword.parse_args(argv)` with `--out-model PATH` (default `models/ok_dann.onnx`) and `--clips-dir PATH`; the ONNX output name is derived from the model file stem (`ok_akane.onnx` → `"ok_akane"`), default unchanged. The negative-phrase list used in training comes from the phrases file's `adversarial` list when `--phrases-file` is given.
  - `build_router_model.sh [name] [modelfile]` — defaults `dann-router` and `models/dann-router.Modelfile`.

- [ ] **Step 1: Write failing tests**

```python
def test_generate_defaults_keep_ok_dann():
    args = gen.parse_args([])
    assert gen.load_phrases(args.phrases_file)[0][0] == "ok dann"

def test_generate_reads_phrases_file(tmp_path):
    f = tmp_path / "p.yaml"; f.write_text("positive: [okay uh-kane]\nadversarial: [okay cane]\n")
    pos, adv = gen.load_phrases(gen.parse_args(["--phrases-file", str(f)]).phrases_file)
    assert pos == ["okay uh-kane"] and adv == ["okay cane"]

def test_train_output_name_from_model_stem():
    assert train.output_name(Path("models/ok_akane.onnx")) == "ok_akane"
```

(`load_phrases(path: Path | None) -> tuple[list[str], list[str]]` and `output_name(path: Path) -> str` are new helpers in the respective scripts. If importing either script pulls in Piper/torch at module level, move those imports inside `main()`.)

- [ ] **Step 2: Run to verify they fail** — `$PY -m pytest tests/scripts -v` → FAIL.

- [ ] **Step 3: Implement** the arg parsing, helpers, and the shell script's positional defaults.

- [ ] **Step 4: Verify** — `$PY -m pytest -q` → all pass; `bash -n scripts/wakeword/build_router_model.sh` → no output.

- [ ] **Step 5: Commit**

```bash
git add scripts tests/scripts
git commit -m "Let wake-word and router-model scripts take a persona's phrases and names"
```

---

### Task 7: Docs, example config, and Dann compatibility check

**Files:**
- Modify: `CLAUDE.md` (persona block, `data_dir`, `config.local.yaml`, `PND_*` env vars with `DANN_*` fallbacks, `claude_server`, `/chat/client`, remove the "`~/.dann` is a legacy name, not worth renaming" note), `README.md` if it documents config/env vars
- Create: `docs/persona-config.md` — the `persona:` block with defaults, the local overlay rules (deep merge; lists replace), and the env var table

- [ ] **Step 1: Write the docs.**

- [ ] **Step 2: Full suite** — `$PY -m pytest -q` → all pass.

- [ ] **Step 3: Dann compatibility check (no commits in dann-of-thursday).** Dann's working tree has uncommitted changes on `launcher-tests`; don't touch them. Instead:

```bash
cd /Users/prestonharms/Git/r3dpnd/dann-of-thursday/runtime
git fetch /Users/prestonharms/Git/r3dpnd/pnd-mcp persona-agnostic
git checkout FETCH_HEAD          # detached, temporary
cd .. && .venv/bin/python -m pytest -q          # Dann's own suite, incl. config.example.yaml vs runtime checks
.venv/bin/python -m pytest runtime/tests -q
cd runtime && NO_VOICE=1 ../.venv/bin/python -m uvicorn app.main:app --port 8765 & 
sleep 8 && curl -s localhost:8765/api/v1/persona     # expect {"name":"Dann","wake_phrase":"ok Dann"}
kill %1
git checkout 3e8a31c   # (still in runtime/) restore the pinned commit
```

Expected: both suites pass; persona endpoint returns Dann; `git -C /Users/prestonharms/Git/r3dpnd/dann-of-thursday status` shows the same changes as before (the `runtime` pointer unchanged).

- [ ] **Step 4: Commit**

```bash
git add CLAUDE.md README.md docs/persona-config.md
git commit -m "Document persona config, local overlay, and PND_* env vars"
```

Do **not** push or open a PR; report back so the user decides.
