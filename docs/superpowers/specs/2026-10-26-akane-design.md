# Akane — Design

**Date:** 2026-10-26 (amended 2026-11-04, see §13)
**Status:** Phase 1 done (in pnd-mcp); Phases 2–3c approved to plan
**Repo:** `R3dPnd/akane` (local: `~/Git/r3dpnd/akane`)

## 1. Intent

Akane is a local voice AI assistant ("**ok Akane**", pronounced *uh-KANE*) that
**replaces Dann of Thursday**. Where Dann was being pointed at coding and Godot
work, Akane is a **thinking partner**: something to talk to out loud that

- helps plan the day,
- turns project ideas into build plans,
- digs into research topics, and
- lets the user talk through whatever they're currently thinking about,

and — the part that makes it more than a chatbot — **keeps a durable record**:
it tracks the user's thinking per topic over time and writes up research it
comes across, so nothing from a conversation is lost.

Akane starts with a fresh, narrow focus, but the infrastructure must make it
cheap to switch Dann's other abilities (coding partner, dev pipeline, Godot,
gardening/BJJ logs, system control) back on later by config, and to add a
Godot editor integration.

## 2. Goals

1. A new persona repo, `akane`, structured like `dann-of-thursday`: the shared
   runtime (`pnd-mcp`) as a `runtime/` submodule, a launcher, and a persona
   `config.yaml`.
2. An "ok Akane" wake-word model trained for the *uh-KANE* pronunciation.
3. Day-one abilities: **day planning** (calendar + reminders), **project build
   plans**, **research with written-up findings**, **thinking out loud with
   per-topic thought tracking**.
4. Akane's own **notebook**: a local store of thought logs, plans and research
   notes, written in the **pnd-notes note format** so the user can promote a
   note into `pnd-notes` by copying the file.
5. **Read-only access to `pnd-notes`**, so Akane can use already-curated
   knowledge.
6. `pnd-mcp` made genuinely persona-agnostic: data directory, display name,
   wake-word label, and ports come from persona config, not hardcoded "Dann".
7. Every Dann capability exists as an **optional module** Akane can enable in
   config with no code change.
8. A **Godot editor plugin** (planned in the infrastructure; built in a later
   phase — see §8).
9. **Claude is the heavy thinker, never a wait** (added 2026-11-04): the local
   model answers every live turn quickly; depth comes from Claude in background
   jobs Akane announces when done (§6.5, §6.6).
10. **Web lookup and opening Mac apps** by voice (§6.7).
11. **Action plans** for any goal, not only software projects (§6.6).
12. **Job applications:** tailor the user's Word resume and a cover letter to a
    posting, PDF on request, and track applications (§6.8).
13. **A calm UI that follows the conversation**, styled as Akane (§6.9), and a
    **distinct voice** (§6.10).
14. **Portable to a more powerful Mac later**: moving machines means cloning,
   running setup, and choosing bigger models in a machine-local config — no
   code edits.

## 3. Non-goals

- Migrating Dann's data (`~/.dann/` notes, history, focus areas). Akane starts fresh.
- Akane writing into `pnd-notes`. It stays read-only and hand-curated; the user promotes.
- Running Dann and Akane side by side. Akane replaces Dann; only one persona runs
  on a machine at a time.
- Shipping the Godot plugin in the first build (infrastructure and design only;
  see phasing).
- Cloud hosting or a billed Claude API dependency.

## 4. Anti-goals (would be a failure even if it "works")

- Akane silently writing to `pnd-notes` or to Dann's `~/.dann/` data.
- The record-keeping being so noisy (every utterance saved) that the notebook
  is useless to read — or so shy that research the user cared about is lost.
- Moving to the new Mac requiring code changes or hand-editing paths in the repo.
- Claude usage drifting onto a billed API key instead of the user's subscription.
- Breaking `dann-of-thursday` while `pnd-mcp` is being generalized, before
  Akane is ready to take over.

## 5. Constraints and decisions already made

| Decision | Source |
|---|---|
| Name **Akane**, wake phrase **"ok Akane"**, pronounced **uh-KANE** | User |
| Akane **replaces** Dann; never run concurrently | User |
| Akane keeps **its own notes**; user **promotes** to `pnd-notes` by hand | User |
| **Start fresh**: no Dann data; Dann's other abilities exist as modules, off by default | User |
| **Godot plugin** directly in the Godot editor, planned as part of the infrastructure | User |
| Keep the **local Ollama backbone** (local model routes every turn) | User |
| **Claude consolidation**: Claude work goes through the `claude` CLI on the user's subscription, not a billed API | User (matches existing `ask_claude` / `web_search`) |
| Must run on a **more powerful Mac** later | User |
| Build in `~/Git/r3dpnd/akane` (already cloned, empty) | User |
| Plan before implementing | User |

Existing system facts the design relies on:

- `pnd-mcp` (`dann-of-thursday/runtime/`) provides: voice pipeline (openWakeWord
  → faster-whisper → Ollama router → Piper), `MCPManager` with
  `list_modules`/`enable_module`/`disable_module` and `always_on`, the FastAPI
  dashboard API, React/Electron UI, and tool-servers `claude_code_server`
  (which also holds `ask_claude` and `web_search`), `devteam`, `schedule`
  (Google Calendar), `notes` (notes + reminders), `gardening`, `bjj`,
  `system`, `focus_areas`.
- Routing is configured as an `agents:` list in `config.yaml`, compiled into the
  Ollama system prompt (`shared/agents_config.py`).
- **Dann is hardcoded in pnd-mcp** in these places, which Phase 1 must fix:
  - Data dir `~/.dann/` in `integrations/servers/_store.py`,
    `shared/focus_areas_store.py`, `app/services/{chat,history,log,metrics,devteam}_service.py`,
    `notes_server.py`, `devteam_server.py`.
  - UI strings: `ui/index.html` title, `VoicePanel.tsx` "Listening for 'ok Dann'",
    `electron/main.cjs` window title and `DANN_CONFIG_PATH`/`DANN_FULLSCREEN` env vars,
    `app/core/config.py` / `app/main.py` project name.
  - Wake-word training phrases hardcoded to "ok dann" variants in
    `scripts/wakeword/generate_wakeword_samples.py`.
  - Router Modelfiles named `dann-router*`.
  - Ports 8000/3000 fixed in the launcher (`launcher/paths.py`).
- `godot-mcp` (third-party, `mkdevkit/godot-mcp`) already ships a Godot editor
  plugin + Node MCP server (WebSocket :6505, ~173 editor-control tools).

## 6. Architecture

```
                    ┌──────────────────────── akane (persona repo) ───────────────────────┐
 "ok Akane" ──mic──▶│ launcher (akane dev/start/stop) ── config.yaml + config.local.yaml   │
                    │        │                                                            │
                    │        ▼                                                            │
                    │  runtime/ (pnd-mcp submodule)                                       │
                    │   voice pipeline → Ollama router (local) ─┬─ answers itself         │
                    │   FastAPI + dashboard UI                  ├─ MCP tools ──┐          │
                    │                                           │              │          │
                    └───────────────────────────────────────────┼──────────────┼──────────┘
                                                                │              │
          always on: notebook, claude (ask/web_search),         │              │ optional modules:
          schedule, notes/reminders, pnd-notes (read-only) ◀────┘              └▶ claude_code, devteam,
                                                                                  godot, gardening, bjj,
                                                                                  system
   Data: ~/.akane/   (notebook/, notes.json, history.jsonl, logs, tokens)
   Claude: `claude` CLI on the user's subscription (one shared bridge)
   Godot editor ◀── WebSocket ──▶ godot module (Phase 4)
```

### 6.1 Phase 1 — Make pnd-mcp persona-agnostic

Add a **`persona:` block** to the config schema and read it everywhere Dann is
hardcoded today:

```yaml
persona:
  name: Akane                 # display name: UI title, window title, status text, logs
  wake_phrase: "ok Akane"     # shown in the UI ("Listening for 'ok Akane'")
  data_dir: ~/.akane          # replaces every ~/.dann reference
  api_port: 8000
  ui_port: 3000
```

- Defaults preserve today's behavior exactly (`name: Dann`, `data_dir: ~/.dann`,
  8000/3000) so `dann-of-thursday` keeps working unchanged until it is retired.
- One helper (e.g. `shared/persona.py`) resolves these; all services and
  tool-servers call it instead of building `Path.home() / ".dann"`. MCP
  tool-servers run as subprocesses, so the data dir is passed down via an env
  var set by `MCPManager` (e.g. `PND_DATA_DIR`).
- Rename `DANN_CONFIG_PATH` → `PND_CONFIG_PATH` (accept the old name as a
  fallback during the transition).
- UI fetches persona name/wake phrase from the API (existing state endpoint or a
  new `/api/v1/persona`) rather than hardcoding. Internal identifiers like
  `useDannStore` may be renamed opportunistically but are not required.
- Wake-word sample generator takes the phrase list as arguments/config instead of
  hardcoded "ok dann" variants, plus an adversarial list.
- Router Modelfile is persona-neutral or per-persona (e.g. `akane-router.Modelfile`
  in the persona repo).
- **Claude consolidation:** split the general Claude bridge (`ask_claude`,
  `web_search`) out of `claude_code_server` into its own module (e.g.
  `claude_server`) so a non-coding persona can have research/reasoning without
  the project/coding tools. Both servers share one CLI-invocation helper so
  there is exactly one place that shells out to `claude`.
- **Machine-local override:** the runtime merges an optional
  `config.local.yaml` (gitignored) over `config.yaml`. Machine-specific things go
  there: Ollama model choice, Whisper model size, audio devices, absolute paths.

### 6.2 Phase 2 — Akane persona repo

Mirror `dann-of-thursday`:

```
akane/
  runtime/            submodule → pnd-mcp (pinned to the Phase 1 commit)
  akane.py            thin entry → launcher.cli.main
  launcher/           ported from dann-of-thursday (paths/readiness/processes/
                      supervisor/discovery/commands/cli), renamed dann→akane,
                      ports read from config
  config.example.yaml persona block, routing prompt, agents, modules
  config.local.example.yaml   machine-specific overrides template
  models/             (gitignored) ok_akane.onnx, akane-router Modelfile lives in repo
  integrations/servers/   persona-specific servers if any (see 6.3)
  tests/unit, tests/integration   ported launcher tests; config checked against runtime
  scripts/setup.sh    one-shot setup for a fresh Mac (see §7)
  training/           (gitignored) wake-word clips
  CLAUDE.md, README.md
```

**Routing (`agents:`) at launch:**

| Agent | Tools | Purpose |
|---|---|---|
| `local` | — | small talk, confirmations, simple facts |
| `plan_day` | schedule (`list_events`, `create_event`, `find_event`), reminders, notebook | "help me plan my day" — reads calendar + open threads, proposes a plan, saves it as today's daily note. **Calendar events are only created after the user explicitly confirms out loud** (see below) |
| `plan` | background Claude job (§6.6) | turns a goal or project idea into an **action plan** (phased build plan for software; concrete next steps for anything else, e.g. "get my finances sorted"); saved to the notebook, announced when done. Replaces `build_plan` (amended 2026-11-04) |
| `deep_think` | background Claude job (§6.6) | "think harder about that" / "ask Claude": sends the recent conversation + the topic's notebook context to Claude; answer is announced and appended to the topic (amended 2026-11-04) |
| `lookup` | `web_search` (claude_server) | quick factual web lookups answered in the turn ("what time does Costco close"); a few seconds' pause is acceptable. Deep research stays a job (amended 2026-11-04) |
| `apps` | system: `open_app`, `get_volume`, `set_volume`, `lock_screen` | "open Spotify", "volume to 30". `lock_screen` goes through spoken confirmation (amended 2026-11-04) |
| `apply` | applications tools (§6.8) | tailor resume + cover letter to a job posting (background job), make PDFs, list/update applications (amended 2026-11-04) |
| `research` | background Claude job (§6.6) | researches a topic; runs in the background, saves a research note with sources, announced when done |
| `think` | notebook | talking things through; appends to the topic's thought log (topic chosen by semantic matching, §6.3) |
| `recall` | notebook search/read, pnd-notes `search_notes`/`get_note` | "what did we decide about X", "what do I know about Y" |
| `reminders` | `add_reminder`, `list_reminders` | quick reminders |

Optional (disabled) agents present in config with `enabled: false`:
`claude_code`, `devteam`, `godot`, `gardening`, `bjj`. (`system` is now
enabled, as `apps` — amended 2026-11-04.)

Phase 2 ships the agents whose tools already exist (`local`, `lookup`, `apps`,
`reminders`, calendar reads, `recall` over pnd-notes). `think`, `plan`,
`research`, `deep_think`, `plan_day`'s calendar writes and `apply` arrive with
the tools they need in Phases 3–3b.

**Voice persona prompt:** warm, concise, speaks 1–2 sentences; tells the user
when something was saved and where ("saved that to your *home-server* notes").

**Calendar confirmation (user requirement):** Akane never writes to Google
Calendar without an explicit spoken "yes". `plan_day` proposes the blocks it
would add ("want me to put deep work 9 to 11 and the gym at 5 on your
calendar?"), holds them as a pending proposal, and only calls `create_event`
after the user confirms. This needs the pending proposal to survive into the
next turn: today voice history is capped and cleared per session, so the
builder must keep a short-lived pending-action state (e.g. in the orchestrator,
expiring after a couple of minutes or at session end). A "no" or no answer drops
it; the daily note is still saved either way. *My call:* implement the
confirmation as a generic "pending action" mechanism, not calendar-specific,
so later modules (e.g. `system`) can reuse it.

### 6.3 The notebook (Akane's own notes)

A new MCP tool-server, `notebook_server`. **Builder's call** whether it lives in
`pnd-mcp` (generic, reusable by future personas — *recommended*) or the persona
repo's `integrations/servers/`.

**Storage:** plain Markdown files under `<data_dir>/notebook/`, one file per
note, using pnd-notes frontmatter so promotion is a file copy:

```
~/.akane/notebook/
  topics/<slug>.md       running thought log per topic/project (append-only sections, dated)
  plans/<slug>.md        project build plans
  research/<slug>.md     research write-ups with sources
  daily/YYYY-MM-DD.md    day plans
```

```markdown
---
title: Home server rebuild
area: shared              # the pnd-notes area it would be promoted into (best guess)
tags: [homelab, hardware]
summary: One-line gist, kept current as the note grows.
updated: 2026-10-26
kind: topic | plan | research | daily      # Akane-only; ignored by pnd-notes
sources: [https://...]                      # research notes only
---
```

**Tools (draft):** `notebook_append_thought(topic, text)`,
`notebook_save_plan(title, body)`, `notebook_save_research(title, body, sources)`,
`notebook_save_daily(body)`, `notebook_search(query, kind?)`,
`notebook_read(id)`, `notebook_list(kind?, limit?)`.

**What gets saved (anti-goal guard):** Akane saves when (a) the user asks, (b) a
research or build-plan turn produces a write-up, (c) a day plan is agreed, or
(d) in a `think` turn, a decision, open question, or new idea is stated —
summarized, not transcribed verbatim. It always says out loud that it saved.

**Choosing the topic (user requirement: semantic matching):** for a `think`
turn, the notebook server matches what the user said against existing topics
by meaning, not exact name — embeddings from a local Ollama embedding model
(e.g. `nomic-embed-text`) over each topic's title + summary, stored next to the
notebook and refreshed when a topic's summary changes. Above a similarity
threshold, Akane uses the best match (and says which topic it saved to). Below
it, Akane **asks before creating a new topic** ("new topic: home server?"). The
user naming a topic explicitly always wins. Within one voice session, once a
topic is chosen it stays the session's topic until the user changes subject.
*My call:* the same matching is used by `recall` and `notebook_search`, and the
threshold is configurable.

**Open threads (for `plan_day`), my call:** upcoming reminders, plus items in
topic logs explicitly marked as open questions or next steps, plus unfinished
build plans. So thought-log entries carry a simple marker for "open question" /
"next step" / "decision" rather than being pure free text.

**Notebook in context:** when a conversation is about a topic that has a
notebook entry, its summary + latest entries are folded into the prompt (same
mechanism as today's focus-area notes). Builder may implement topics *as*
focus areas if that reuse is clean.

**Promotion:** manual. A small CLI helper (`akane promote <id> [--area X]`) that
copies a note into `../pnd-notes/notes/<area>/` and strips Akane-only fields is
a nice-to-have, not required.

### 6.4 pnd-notes read access

Register `pnd-notes` (Node, `server/pnd-notes.mjs`) in Akane's `mcp.servers`
with its path set in `config.local.yaml` (machine-specific). Tools:
`list_areas`, `search_notes`, `get_note`. Read-only by construction.

### 6.5 Models: Ollama backbone + Claude

- **Ollama (local)** routes every turn and answers simple ones. Default on the
  current machine: the existing qwen2.5:7b-based router, rebuilt as
  `akane-router` with Akane's prompt. Configurable per machine in
  `config.local.yaml`; the bigger Mac can run a larger model (e.g. a 14B/32B
  class model) without code change.
- **Claude (via `claude` CLI, subscription)** handles deep reasoning, build
  plans, and web research through the single `claude_server` bridge.
- Embeddings for topic matching also come from Ollama (local).
- **User decision (2026-11-04): a quick, shallow live reply beats waiting for
  Claude.** Claude never answers a live turn's conversation directly (the
  `lookup` web search is the one in-turn CLI call). All Claude depth arrives
  through background jobs — research, plans, applications, and `deep_think`
  for "think harder about that".
- *My call:* strip `ANTHROPIC_API_KEY` from the environment when invoking the
  `claude` CLI and remove the anthropic-SDK fallback in
  `app/api/v1/endpoints/prompt_builder.py`, so Claude usage can't silently move
  to a billed API.
- Optional, builder's call: a `models.profile` (`small`/`large`) preset in
  `config.local.yaml` that picks Ollama model + Whisper size together.

### 6.6 Background jobs and spoken announcements

User requirement: long research/build-plan work must not make the user wait in
silence; Akane says it's on it, and **speaks up when the work is done**.

- **Job runner (pnd-mcp, generic):** `start_research(topic, question)`,
  `start_plan(title, goal)`, `start_deep_think(topic, question)` and (§6.8)
  `start_tailor_application(posting)` tools enqueue a job and return immediately
  ("I'm on it — I'll let you know"). Jobs run in the background (pattern:
  `devteam_server` + `devteam_service`, state in `<data_dir>/jobs.json`).
- **Claude does the write-up and saves it (my call):** the job calls the
  `claude` CLI once (with its built-in web search for research), asking for
  long-form Markdown with a sources list and a one-sentence spoken summary. The
  job writes the note to the notebook directly (pnd-notes frontmatter, `kind`,
  `sources`). The local router never carries the long body. One CLI call per
  job; no multi-step agent runs. Timeout generous (e.g. 10 min), configurable.
- **Announcing:** on completion the job emits an EventBus event. The voice
  orchestrator gains an **announcement queue**: when the pipeline is idle (not
  recording, transcribing, thinking or speaking), it speaks the queued summary
  via TTS ("Your research on heat pumps is done — short version: …, it's in
  your notebook"). **User decision (2026-11-04): announcements wait until the
  voice session ends** — never mid-conversation; spoken once the orchestrator is
  back to listening for the wake word. *My call:* if an announcement asks a
  question ("want me to try again?"), Akane opens a short listening window
  (~8 s, configurable) that needs no wake word, and the answer goes through the
  pending-action mechanism; silence drops it. The
  dashboard also shows a notification, and failures are announced too ("the
  heat pump research failed — want me to try again?").
- `list_jobs` / `check_job` tools let the user ask "is that research done yet?".
- *My call:* no quiet hours or do-not-disturb in the first build; noted as a
  likely follow-up.

### 6.7 Web lookup and Mac apps (added 2026-11-04)

- `web_search` from `claude_server` is always on and used for the `lookup`
  agent. Same CLI bridge, so still subscription-only.
- The existing `system_server` (`open_app`, `get_volume`, `set_volume`,
  `lock_screen`) is enabled for Akane. `lock_screen` is routed through the
  pending-action confirmation (§6.2) once that exists in Phase 3; in Phase 2,
  `lock_screen` is left out of Akane's tools allowlist rather than run
  unconfirmed. *My call.*

### 6.8 Job applications (added 2026-11-04)

User intent: Akane takes **tailoring the resume and cover letter to each job**
off the user's plate. Akane produces documents; **the user reviews and submits.**
Akane never submits applications or fills web forms.

- **Master resume:** the user's generic resume is
  `/Users/prestonharms/Downloads/Resume.docx` (Word). It is **missing the
  user's current role at Starbucks and enrollment at UW Tacoma**; the builder
  must ask the user for those details (title, dates, bullets; program, expected
  date) and add them. The master copy lives at
  `<data_dir>/applications/master/Resume.docx`; the Downloads file is never
  modified. Its path is configurable (`applications.master_resume` in
  `config.local.yaml`).
- **Input:** the user copies a posting URL or text and says "tailor my resume
  for this job". *My call:* the tool reads the macOS clipboard (`pbpaste`); a
  URL is fetched by Claude, text is used as-is. The posting is saved with the
  outputs.
- **Tailoring (background Claude job):** one CLI call returns structured
  edits — rewritten summary, reordered/reworded bullets per role, skills
  ordering — plus a cover letter body and a short "what I changed" note.
  **Claude must not invent experience, employers, dates, metrics or skills
  absent from the master** (prompt rule plus a check that every employer/date
  in the output exists in the master). Code applies the edits to a **copy of
  the user's .docx**, preserving its styles and layout (e.g. `python-docx`,
  replacing paragraph text while keeping run/paragraph formatting). The cover
  letter is a new .docx using the resume's fonts and header.
- **Output:** `<data_dir>/applications/<company>-<role>/` with
  `Resume.docx`, `Cover Letter.docx`, `posting.md`, `changes.md`.
  Announced when done ("Your Nintendo resume and cover letter are ready — I
  leaned on your Godot and full-stack work").
- **PDF on request** ("make PDFs of those"): export through Microsoft Word,
  which is installed, via AppleScript (`docx2pdf` or equivalent). No other
  converter is on the machine.
- **Tracker:** `<data_dir>/applications/applications.json` — company, role,
  posting URL, date, status (`drafted`/`applied`/`interviewing`/`rejected`/
  `offer`), folder. Tools: `list_applications`, `update_application_status`.
  `plan_day` surfaces follow-ups (e.g. applied >7 days ago, no update). *My call.*

### 6.9 UI: conversation + context (added 2026-11-04)

User feedback: Dann's dashboard is **too busy and doesn't react to the
conversation**; restyle it as Akane. Chosen direction (**B**, from mockups):

- **Home layout:** conversation on the left; a small state orb next to the name
  (breathes/pulses/glows for listening/thinking/speaking — reuse
  `voice/StateOrb.tsx`). On the right, a cream "paper" **context panel** that
  follows the current turn:
  - `think` → the topic: decisions, open questions, next steps, latest entries
  - `plan_day` → today's calendar; proposed blocks drawn as dashed slots until
    confirmed
  - `apply` → the application: posting, resume, cover letter, status
  - `recall` → the matched notes
  - idle/none → today: reminders, open threads, running jobs
- **Top bar:** running jobs as one line ("● researching heat pumps"); nothing else.
- **Everything else** (System, Modules, Logs, Focus Areas, prompt builder)
  moves behind one menu button. Nothing is removed.
- **Look:** akane red (茜色, ~`#b7282e`, highlight ~`#e0575c`) on warm
  near-black (~`#1a1214`), cream paper (~`#f6efe9`) for context cards, muted
  text ~`#8a7d78`. Calm; minimal chrome.
- **Where (my call):** in pnd-mcp's shared UI as a new home layout selected by
  persona config (e.g. `persona.ui.layout: conversation`, `persona.ui.theme`
  tokens). Dann keeps its current dashboard until retired.
- **Backend contract (my call):** each turn (and job completion) publishes a
  `context` event over the existing event stream, e.g.
  `{kind: topic|calendar|application|search|today, id, data}`. The UI renders
  whatever arrives; the panel stays on the last context until a new one
  replaces it or the session ends.
- Mockup: `.superpowers/brainstorm/*/content/ui-direction.html` (option B).

### 6.10 Voice (added 2026-11-04)

- User chose **Piper `en_GB-alba-medium`** (female, light Scottish accent)
  after auditioning four voices. Set as `tts.voice_model` in Akane's config;
  `setup.sh` downloads it from `rhasspy/piper-voices` on Hugging Face. Dann
  keeps `en_US-lessac-medium`.
- Kokoro TTS (more natural, has British female voices) is a possible later
  upgrade on the bigger Mac; out of scope now.

## 7. Portability to a more powerful Mac

- Everything machine-specific lives in **gitignored** files: `config.local.yaml`,
  `models/` binaries, `training/`, `~/.akane/`.
- `scripts/setup.sh` on a fresh Mac: init submodules, create `.venv`, install
  Python + UI deps, check/install Ollama, pull base model, build `akane-router`,
  download Piper voice, copy `config.local.example.yaml` if absent, and verify the
  `ok_akane.onnx` model exists (with instructions to copy it from the old machine
  or retrain).
- The wake-word model is portable (copy the `.onnx`); retraining is optional.
- Notebook portability: `~/.akane/notebook/` is plain Markdown — the user may
  later choose to sync it (git or cloud folder). Not in scope now; the design
  just must not prevent it (no absolute paths inside notes).

## 8. Godot integration (infrastructure planned now, built Phase 4)

User intent: a plugin **directly in the Godot editor**. Builder/designer's read
(**my call — user to confirm**): both directions —

1. **Talk to Akane from inside Godot** — an editor dock (chat panel, mic button
   optional) that sends text to Akane's existing chat API and shows replies.
   It also sends editor context with each message: open scene, selected
   node(s), current script and cursor/selection.
2. **Akane acts in the editor** — reuse `godot-mcp`'s plugin/server (already
   ~173 editor tools over WebSocket :6505) as Akane's optional `godot` module
   rather than rebuilding editor control.

Infrastructure to build *now* so Phase 4 is just the plugin:
- A chat endpoint usable by external clients that accepts an optional `context`
  payload (source + structured data) and folds it into the turn prompt. Generic,
  not Godot-specific. *My call:* today's chat API only works through streams
  bound to a focus area, so add a lightweight client-conversation endpoint
  (conversation id supplied by the client, no focus-area binding required)
  rather than forcing one stream per Godot project.
- `godot` stays registered as an optional module in config.

Phase 4 deliverable: a GDScript `EditorPlugin` addon (e.g. `addons/akane/`)
installable into any project in `pnd-games`. **Builder's call** on where its
source lives; recommended in `pnd-mcp` (persona-agnostic — it talks to whatever
runtime is on the configured port) under `godot/addons/`.

## 9. Phasing

| Phase | Delivers | Done when |
|---|---|---|
| 1. pnd-mcp generalization | persona block, data_dir, ports, UI strings, wake-phrase params, `claude_server` split, `config.local.yaml`, client chat endpoint with `context` payload, API-key stripping | runtime tests pass; `dann-of-thursday` bumped to it runs identically **with no config edits** (compat fallbacks: old env var names still read; `claude_code_server` keeps exposing `ask_claude`/`web_search` by delegating to the shared bridge) |
| 2. Akane talks | repo scaffold, launcher port, config, router model, ok-Akane wake word, **Alba voice**, setup script, pnd-notes registration, **`lookup` (web search) and `apps` (system) enabled**, tests (≥95% launcher coverage like Dann). Runs on the existing dashboard, titled Akane | `akane dev --voice` responds to "ok Akane" (uh-KANE) in the Alba voice; "open Spotify", "what's on my calendar today", "what time does Costco close" and "what do my notes say about X" all work. **Calendar is deferred (user, 2026-11-04):** the schedule module stays off until the groundwork is done |
| 3. Akane remembers and thinks | `notebook_server` with semantic topic matching, prompt folding, background job runner + spoken announcements (`research`, `plan`, `deep_think`), pending-action confirmation (calendar, lock screen), optional promote helper | a think conversation lands in the right topic (or asks first); a research request returns immediately, is announced aloud when done, and leaves a sourced note in pnd-notes format; "think harder about that" returns an announced Claude answer saved to the topic; `plan_day` works from reminders, open threads and application follow-ups without a calendar |
| 3b. Applications | master resume (Starbucks + UW Tacoma added, with the user), tailoring job, cover letter, PDF export via Word, applications tracker | from a copied posting, Akane announces a tailored `Resume.docx` + `Cover Letter.docx` that keep the original formatting and invent nothing; "make PDFs" produces PDFs |
| 3c. Akane UI | conversation + context home layout, context events from the backend, Akane theme, busy panels behind a menu | while talking, the right panel switches between topic, calendar, application and today as the conversation moves |
| 3d. Calendar hookup | user creates a Google OAuth client and signs in into `~/.akane` (guided); choose primary vs a dedicated "Akane" calendar; enable schedule module; calendar in `plan_day` + context panel | "what's on my calendar today" works; a day plan only touches the calendar after a spoken yes |
| 4. Godot plugin | editor dock addon talking to Akane; `godot` module wiring | from inside Godot, ask Akane about the selected node and get an answer that uses that context |
| 5. Retire Dann | archive `dann-of-thursday` (README pointer to Akane) | user decides when |

## 10. Left to the builder

- Exact module/function names, the persona helper's shape, env var names.
- Whether notebook topics are implemented on top of focus areas or separately.
- Where `notebook_server` and the Godot addon source live (recommendations above).
- Test strategy details, following the existing repos' conventions (pytest unit +
  integration; integration tests never touch a real running assistant).
- Whether to rename internal `Dann*` identifiers in the UI code.

## 11. Resolved with the user (2026-10-26)

1. Long research/build-plan work runs in the background; **Akane speaks up when it's done** (§6.6).
2. Topics are chosen by **semantic matching**, asking before creating a new one (§6.3).
3. Akane may add calendar events **only after explicit spoken confirmation** (§6.2).

## 12. Calls made by the designer (check these)

- Backward-compat fallbacks in pnd-mcp so Dann needs no config edits during the transition.
- Claude writes and saves the long-form research/plan itself; one CLI call per job; the router only speaks the summary.
- Pending-action confirmation is generic, not calendar-only.
- "Open threads" = reminders + marked open questions/next steps in topic logs + unfinished plans; so thought-log entries carry simple markers.
- Embeddings for topic matching via a local Ollama embedding model; threshold configurable.
- No quiet hours / do-not-disturb for announcements in the first build.
- Godot: both directions (editor chat dock + `godot-mcp` editor control), with a new client chat endpoint — **still to be confirmed by the user**; it doesn't block Phases 1–3.
- `notebook_server`, job runner and Godot addon source recommended to live in pnd-mcp (persona-agnostic).
- Remove the anthropic-SDK fallback and strip `ANTHROPIC_API_KEY` for CLI calls.

## 13. Amendment — resolved with the user (2026-11-04)

1. Claude is the heavy thinker, but **quick shallow local replies beat waiting**; Claude depth arrives only via announced background jobs (§6.5).
2. New tools: **web search**, **opening Mac apps** (§6.7), **action plans** for any goal (§6.6), **resume + cover letter tailoring** (§6.8).
3. Applications: **Word format kept**, PDF on request; Akane stops at documents, the user submits. Master resume needs **Starbucks role and UW Tacoma enrollment** added.
4. UI: dashboard was busy and static → **layout B, conversation + context panel**, Akane styling (§6.9).
5. Voice: **female, subtle accent → Piper `en_GB-alba-medium`** (§6.10).
6. Order: Phase 2 (talks) → 3 (remembers/thinks) → 3b (applications) → 3c (UI) → 4 Godot → 5 retire Dann.

Designer calls added on 2026-11-04: `deep_think` as a job, not a live Claude
reply; `build_plan` widened into `plan`; clipboard as the posting input;
structured edits applied to a .docx copy (not regenerating the document);
applications tracker + follow-up nudges in `plan_day`; `lock_screen` excluded
until confirmation exists; UI lives in pnd-mcp selected by persona config, with
a generic `context` event contract.

### Settled after the builder check (2026-11-04, designer calls)

- **Agent = tool chosen (no separate classifier step).** The turn's agent is
  inferred from the tools the router calls. To make that reliable, `think`
  and `recall` turns are expected to call a notebook tool (prompt rule), and
  context folding happens inside notebook tools' results rather than as a
  pre-step. Tool count for the 7B router is kept lean via the per-server
  tools allowlist. Revisit an explicit classifier on the bigger Mac if routing
  quality is poor.
- **Voice and typed chat share the behaviour.** Pending actions, session topic,
  notebook folding and `context` events live in a shared service used by both
  the orchestrator and `chat_service`, so typed chat can never write the
  calendar or lock the screen without confirmation. The 3c conversation pane
  keeps a small text input under the transcript.
- **Topic tidying via Claude, once per session.** During a `think` turn the
  local model appends the entry with its marker immediately. When the voice
  session ends (or after 10 idle minutes for typed chat), one background
  Claude job per touched topic rewrites that topic's summary and cleans up
  markers; embeddings are refreshed after. No announcement for tidy jobs.
- **Calendar deferred (user, 2026-11-04).** Google Calendar has never been
  connected (no credentials in `~/.dann`). It moves to Phase 3d, after the
  groundwork; the user will be walked through OAuth setup then.
