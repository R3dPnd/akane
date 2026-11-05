# Akane User Guide

Akane is a local voice assistant and thinking partner for your Mac. You can
talk to her ("ok Akane", said *uh-KANE*) or type to her. She answers in a warm
Scottish voice and keeps her own notes in `~/.akane`.

- **Fast, local replies.** A local model (`akane-router`, built on qwen3:8b via
  Ollama) handles every turn, so nothing waits on the cloud just to answer you.
- **Claude for the heavy lifting.** Web lookups go through Claude today. Deeper
  research, action plans and "think harder" come in Phase 3. All Claude use goes
  through the `claude` CLI on your subscription, never a billed API key.

This guide covers Phase 2: what Akane can do now, how to run her, and what to
do when something goes wrong.

---

## 1. Quick start

```bash
akane dev --speak   # type to her, hear her answer (mic never on)
akane dev --voice   # talk or type; she listens for "ok Akane"
akane stop          # shut everything down
```

The `akane` command works from any directory.

---

## 2. Choosing a mode

| You want to… | Run | Mic | Akane speaks | Window |
|---|---|---|---|---|
| Type and hear her reply out loud | `akane dev --speak` | **never opened** | yes | browser tab |
| Talk to her (and type) | `akane dev --voice` | listening for "ok Akane" | yes | fullscreen app window |
| Type silently | `akane dev` | off | no | browser tab |
| Voice with no dashboard | `akane start` | listening | yes | none (terminal only) |

- In `--speak` mode the wake-word detector and speech-to-text never load. The
  mic is never opened, so nothing you say is heard or recorded.
- In `--voice` mode a reply to something you typed waits until any spoken
  conversation has finished, so she never talks over herself or you.
- The dashboard opens at <http://localhost:3000>; its API runs on port 8000.

---

## 3. Command-line reference

```
akane <command> [options]
```

### `akane dev` (alias: `akane code`)

Starts the API and the dashboard, then opens it.

| Option | Effect |
|---|---|
| *(none)* | Text only, in a browser tab. Akane stays silent. |
| `--speak` | Akane reads her replies to typed chat aloud. The mic is never opened. |
| `--voice` | Akane listens for "ok Akane" and speaks. Opens a fullscreen Electron window. |
| `-h`, `--help` | Show help. |

`--speak` and `--voice` can't be combined; asking for both is an error.

### `akane electron`

Same as `dev`, but the dashboard runs inside an Electron window with hot reload
(for working on the UI itself). Takes the same `--voice` / `--speak` options.

### `akane start`

Only the API and the listening voice pipeline, with output written straight to
the terminal. There's no dashboard. Useful when you only want to talk.

### `akane stop`

Stops every Akane process: the launcher, API, dashboard and window. That
includes processes orphaned by a terminal you closed. It never touches Dann's
processes.

### `akane restart`

Stops the running Akane and starts it again with the **same** command and
options (e.g. `dev --speak`), so you don't have to retype them. You can also
restart from the dashboard's restart button, or by saying "restart Akane" /
"restart yourself".

### `akane --help`

Lists the commands. `akane <command> --help` shows a command's options.

### Before anything starts: startup checks

`dev`, `electron` and `start` first check your machine. Each problem is printed
on one line along with the command that fixes it:

| Message | Level | What to do |
|---|---|---|
| `port 8000 (or 3000) is already in use by another program` | stops startup | `akane stop`; if it's still busy, `lsof -i :8000` shows what's using it |
| `wake-word model ok_akane.onnx not found` | stops `--voice` / `start` | copy it from your old Mac into `models/`, or run `scripts/train_wakeword.sh` |
| `Piper voice en_GB-alba-medium not found` | stops `--voice` / `--speak` / `start` | `scripts/setup.sh` |
| `Electron isn't installed correctly, so the app window can't open` | stops `dev --voice` / `electron` | `scripts/fix_electron.sh` |
| `Ollama model akane-router is not built` | warning | `scripts/build_router.sh` |
| `ollama is not installed` | warning | `brew install ollama`, then `scripts/setup.sh` |
| `MCP server pnd_notes is unavailable` | warning | clone `pnd-notes` next to `akane`, then `scripts/setup.sh` |

Warnings don't stop Akane from starting; she just can't use that piece.

---

## 4. Talking to Akane (`--voice`)

1. Say **"ok Akane"** (*uh-KANE*). You'll hear a chime.
2. Say your request. Akane replies and keeps listening, so you can just keep
   going without saying the wake word again.
3. End the conversation with **"goodbye"**, **"thanks Akane"**, **"that's all"**
   or **"we're done"**.

Some things to know:

- **Silence ends a conversation.** After four turns where she hears nothing,
  she quietly stops listening and goes back to waiting for "ok Akane".
- **Mute** with the mic button in the dashboard. While muted she won't respond
  to the wake word, and speaking a typed reply won't unmute her.
- **"Restart Akane"** restarts her (it only happens when you ask).
- Ending a conversation doesn't shut Akane down; `akane stop` or Ctrl+C does.

---

## 5. Typing to Akane

In the dashboard's **AKANE** tab, create or pick a work stream (a
conversation) and type. In `--speak` or `--voice` mode she also reads her
reply aloud. "Clear" starts that conversation fresh.

Typed replies can be longer than spoken ones, so expect a paragraph rather than
a sentence or two.

---

## 6. What Akane can do (Phase 2)

| Ask | What happens | Typical wait |
|---|---|---|
| "open Spotify", "open Notes" | opens the app (she'll say if it isn't installed) | ~7 s |
| "what's the volume?", "set the volume to 30" | reads or sets the Mac's volume | ~7 s |
| "remind me to call the dentist tomorrow", "what are my reminders?" | saves or lists reminders in `~/.akane/notes.json` | ~7 s |
| "what time does Costco in Tacoma close today?", "weather in Seattle tomorrow" | quick web lookup through Claude | 10–30 s |
| "what do my notes say about kubernetes?" | searches your **pnd-notes** knowledge base, read-only | ~7–10 s |
| small talk, thinking out loud, simple facts | answers directly | 2–3 s |

Things she can't do yet (and will say so):

- **Calendar:** Google Calendar isn't connected yet (Phase 3d).
- **Lock the screen:** waits until she can ask "are you sure?" (Phase 3).
- **Saving thoughts by topic, research write-ups, action plans, "think
  harder", resume tailoring:** Phase 3 and 3b.

She never writes to your pnd-notes; that knowledge base is read-only to her.

---

## 6b. Job hunting

Akane finds part-time and gig work that fits your schedule, using your
**pnd-job-search** app as the engine. It's set up once:

```bash
akane jobs-app install                          # build the app and run it in the background (always on)
akane jobs-app load-resume ~/Downloads/Resume.docx   # make this your active resume
akane jobs-app status                           # running? healthy? JSearch key set? (never prints the key)
akane jobs-app uninstall                        # stop the background service
```

The app needs PostgreSQL (`brew services start postgresql@16`), and a
**JSearch** key from RapidAPI in `~/Git/r3dpnd/pnd-job-search/.env` as
`JOBS_API_KEY=…`. Without the key, Akane still finds gig work but no
job-board postings, and the report says so.

**Run a hunt:**

```bash
akane hunt
```

1. Searches the job boards (through JSearch) for your `job_hunt` kinds in each
   of your locations.
2. Asks Claude to find async gig work: AI code evaluation and training, code
   review, bounties.
3. Has Claude screen everything against your resume and constraints.
4. Drops anything under your pay floor (yearly and monthly pay are converted
   to hourly first) or with a dead link.
5. Writes the top leads to `~/.akane/applications/reports/<date>.md`, each
   with pay, a score, why it fits, a suggestion and the link.

Leads already reported never come back. Running it again the same day adds
any new ones to the same report, continuing the numbers.

Your criteria live in `config.local.yaml` under `job_hunt:` (see
`config.local.example.yaml`): pay floor, locations, kinds of work, schedule,
deal-breakers, and how many leads to keep.

Coming next: the report read to you in the morning, "tailor my resume for
3", "dismiss 2", "I applied to 1", and the hunt running automatically
overnight.

## 7. The dashboard

- **Header:** Akane's name, her current state (idle, listening, thinking,
  speaking), and the connection light.
- **AKANE tab:** your typed conversations, plus the voice panel on the right
  with the state orb and recent spoken turns.
- **Focus areas, Modules, Notes, Metrics, System:** what Akane focuses on,
  which tool modules are active, your notes, turn timings, and machine/model
  load.
- **Logs** (bottom bar): live events, useful when something seems off.

The rose color theme comes from `persona.theme: rose` in `config.yaml`.

---

## 8. Configuration

### `config.yaml` (tracked; this file *is* Akane)

| Setting | What it controls | Current |
|---|---|---|
| `persona.name` / `wake_phrase` | name shown in the UI and used in spoken commands | Akane / "ok Akane" |
| `persona.data_dir` | where her data lives | `~/.akane` |
| `persona.api_port` / `ui_port` | ports | 8000 / 3000 |
| `persona.theme` | dashboard colors | `rose` |
| `wake_word.threshold` | wake-word sensitivity: higher means fewer false wakes but more misses | 0.7 |
| `ollama.model` | the local model | `akane-router` |
| `ollama.temperature` | kept low so she reliably uses her tools | 0.1 |
| `tts.voice_model` | her voice | Piper `en_GB-alba-medium` |
| `ux.speak_typed_replies` | read typed replies aloud | true |
| `agents:` | what she can route to; Phase 3 agents are present but `enabled: false` | |
| `mcp.servers:` | tool servers; always-on ones each list the tools she may use | |

Paths in `config.yaml` are relative to `runtime/`, so `../models/…` means
this repo's `models/` folder.

### `config.local.yaml` (this machine only; not in git)

Created by setup from `config.local.example.yaml`. It's merged over
`config.yaml`, so put machine-specific overrides here: a bigger model, a bigger
Whisper model, a particular mic or speaker. Note that lists replace whole lists,
so to override `mcp.servers` you copy the entire list.

```yaml
ollama:
  model: akane-router-14b    # a bigger router on a bigger Mac
stt:
  model_size: medium         # better transcription, more memory
audio:
  input_device: "MacBook Pro Microphone"
```

---

## 9. Setting up a Mac

Clone `akane` next to `pnd-notes` (e.g. both in `~/Git/r3dpnd/`), then:

```bash
git clone --recurse-submodules https://github.com/R3dPnd/akane.git
cd akane
scripts/setup.sh
```

`setup.sh` is safe to re-run. It:

- creates the Python venv and installs the dependencies, the dashboard and Electron
- pulls `qwen3:8b` and builds `akane-router`
- downloads the Piper voices
- installs the `akane` command into `~/.local/bin`
- creates `~/.akane` and `config.local.yaml`

The one thing it doesn't make is the wake-word model: copy
`models/ok_akane.onnx` from your old Mac, or train one (next section).

### Helper scripts

| Script | When to use it |
|---|---|
| `scripts/setup.sh` | first install, or to repair a broken install |
| `scripts/build_router.sh` | after editing `models/akane-router.Modelfile` |
| `scripts/train_wakeword.sh` | to (re)train "ok Akane" (10–20 min) |
| `scripts/fix_electron.sh` | when the app window won't open ("Electron failed to install correctly") |

---

## 10. Improving the wake word

The bundled model was trained on synthetic voices only. If she misses you a lot
or wakes on her own, record your own voice (it makes the biggest difference):

```bash
.venv/bin/python runtime/scripts/wakeword/record_wakeword_samples.py --count 40
```

The recorder's prompts still say "ok Dann"; say **"ok Akane"** instead. Then
move the clips from `runtime/training/positive_real/` to
`training/positive_real/` and retrain with `scripts/train_wakeword.sh`.

For a quick fix in the meantime, raise `wake_word.threshold` (e.g. to `0.8`)
in `config.local.yaml`.

---

## 11. Troubleshooting

| Symptom | Likely cause and fix |
|---|---|
| `akane: command not found` | `~/.local/bin` isn't on your PATH: `echo 'export PATH="$HOME/.local/bin:$PATH"' >> ~/.zshrc`, then open a new terminal. |
| "port 8000 is already in use" | Another program, or an old Akane, has the port: `akane stop`, then `lsof -i :8000` if it's still busy. |
| App window doesn't open; "Electron failed to install correctly" | `scripts/fix_electron.sh` (npm's Electron install breaks on Node 26). |
| She says she did something but nothing happened | Check **Logs** for a `Calling tool` line. Rephrase more directly ("set a reminder to…"). The local model occasionally skips a tool. |
| She wakes up on her own | Room sound near the threshold, or her own voice. Raise `wake_word.threshold`, or record your voice (section 10). |
| She doesn't hear "ok Akane" | Say *uh-KANE*, a little louder. Check the mic isn't muted in the dashboard. Record your voice (section 10). |
| Web lookups fail | Make sure you're signed in to the `claude` CLI: run `claude` once in a terminal. |
| "what do my notes say…" finds nothing | Is `pnd-notes` cloned next to `akane`? Startup warns if it isn't. |
| Replies are slow | The first turn after a long idle reloads the model (up to ~30 s). After that, ~7 s for actions and 2–3 s for small talk. |

Logs and history live in `~/.akane/akane.log` and `~/.akane/history.jsonl`.

---

## 12. Your data

Everything stays on your Mac:

| Path | What |
|---|---|
| `~/.akane/notes.json` | reminders |
| `~/.akane/history.jsonl` | conversation history |
| `~/.akane/akane.log` | logs |
| `models/ok_akane.onnx` | your wake-word model |

The only thing that leaves the machine is web lookups, which Claude runs
through your subscription. Akane never reads or writes Dann's `~/.dann`.
