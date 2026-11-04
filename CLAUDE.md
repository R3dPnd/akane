# Akane — notes for Claude Code sessions

Akane is a local voice assistant ("ok Akane", said *uh-KANE*) and thinking
partner. It replaces Dann of Thursday. This repo is the **persona**: config,
launcher, models and scripts. The voice pipeline, MCP tool-servers and
dashboard all live in the shared runtime, `runtime/` (the pnd-mcp submodule).

Design: `docs/superpowers/specs/2026-10-26-akane-design.md`. Phase plans:
`docs/superpowers/plans/`.

## Commands

```bash
scripts/setup.sh                      # fresh-Mac setup; re-runnable
akane dev --voice                     # API + UI + voice, Electron window
akane dev                             # API + UI, no voice, browser tab
akane stop                            # stop every Akane process (never Dann's)
.venv/bin/pytest tests --cov=launcher # keep launcher coverage ≥95%
scripts/build_router.sh               # rebuild akane-router after editing its Modelfile
scripts/train_wakeword.sh             # retrain models/ok_akane.onnx
```

## Rules that aren't obvious from the code

- **Paths in `config.yaml` are relative to `runtime/`**, because every child
  process runs with `cwd=runtime/`. `../models/x` is this repo's `models/`;
  `../../pnd-notes` is the sibling clone.
- `config.yaml` is tracked (it *is* Akane, with no secrets). Anything specific
  to one machine goes in `config.local.yaml` (gitignored, merged over it). Lists
  in the overlay replace whole lists.
- Every `always_on` MCP server has a `tools:` allowlist, and allowlists must not
  share names (pnd-mcp's `notes_server` and pnd-notes both have `search_notes`).
  `tests/integration/test_persona_config.py` enforces this.
- Claude is used only through the `claude` CLI (`claude_server`) on the user's
  subscription. Never add the anthropic SDK or an API key.
- Don't edit `runtime/` from here. A runtime change is a pnd-mcp commit, then a
  submodule bump.
- Never write to `~/.dann`, `dann-of-thursday`, or `pnd-notes` (read-only).
- `akane` is a symlink, `~/.local/bin/akane` → `akane.py` (made by setup.sh).
  `akane.py` re-executes itself under `.venv/bin/python` (`launcher/venv.py`),
  so it works whatever `python3` is first on PATH. Keep `launcher/venv.py`
  stdlib-only.
- Preflight (`launcher/preflight.py`) runs before every launch. Add a check
  there when a new model or sibling repo becomes required.

## Data

`~/.akane/` (from `persona.data_dir`): reminders/notes, history, logs. The model
binaries in `models/` and `models/piper/` are gitignored. Copy
`models/ok_akane.onnx` between machines or retrain it.
