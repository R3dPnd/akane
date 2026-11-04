# Akane

A local voice assistant and thinking partner for macOS. Say **"ok Akane"**
(*uh-KANE*). Akane answers in a warm Scottish voice (Piper `en_GB-alba-medium`).

- **Quick replies** come from a local model (`akane-router`, built on
  qwen3:8b), so a live turn never waits on the cloud.
- **Claude is the heavy thinker.** Web lookups now; later, research, action
  plans and "think harder" run as background jobs that Akane announces when
  they're done. All of it goes through the `claude` CLI on your subscription,
  never a billed API key.

Akane replaces Dann of Thursday and runs on the same shared runtime,
[pnd-mcp](https://github.com/R3dPnd/pnd-mcp) (`runtime/`).

## What it can do today (Phase 2)

| Say | What happens |
|---|---|
| "ok Akane, open Spotify" | opens the app |
| "set the volume to 30" | sets the volume |
| "what time does Costco close today?" | quick web lookup via Claude |
| "remind me to call the dentist tomorrow" | saves a reminder in `~/.akane` |
| "what do my notes say about …" | searches your pnd-notes (read-only) |

**Typing instead of talking:** Akane reads her replies to typed chat aloud.
`akane dev --speak` does this *without ever listening*: no wake word, no mic.
With `akane dev --voice` she also listens, and typed replies wait if she's
mid-conversation.

Coming next (see `docs/superpowers/specs/2026-10-26-akane-design.md` §9):

- **3:** a notebook of topics and Claude research/plan jobs, plus a spoken "yes" before anything risky
- **3b:** resume and cover-letter tailoring
- **3c:** the new conversation + context UI
- **3d:** Google Calendar

## Setup on a new Mac

Clone it next to `pnd-notes` (e.g. both in `~/Git/r3dpnd/`), then:

```bash
git clone --recurse-submodules https://github.com/R3dPnd/akane.git
cd akane
scripts/setup.sh
```

Setup makes the venv, puts an `akane` command in `~/.local/bin`, installs the UI, pulls the base model and builds
`akane-router`, downloads the Piper voices, and creates `~/.akane` and
`config.local.yaml`. For the wake word, copy `models/ok_akane.onnx` from the old
machine, or run `scripts/train_wakeword.sh` (10–20 min). On a more powerful Mac,
put a bigger model or Whisper size in `config.local.yaml`; no code changes.

## Running

```bash
akane dev --voice   # talk and type; she listens and speaks (Electron window)
akane dev --speak   # type only; she speaks her replies, mic never opened
akane dev           # type only, silent (browser tab)
akane stop
```

If something's missing (a model, a busy port because Dann is still running),
Akane says what's wrong and what to run before it starts.

## Tests

```bash
.venv/bin/pytest tests --cov=launcher
```
