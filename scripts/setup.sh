#!/usr/bin/env bash
# One-shot, re-runnable setup for Akane on a fresh Mac. Safe to run again:
# every step skips what's already done.
set -euo pipefail
cd "$(dirname "$0")/.."
REPO="$(pwd)"

say() { printf '\033[36m[akane setup]\033[0m %s\n' "$*"; }
warn() { printf '\033[33m[akane setup] %s\033[0m\n' "$*"; }

say "Runtime submodule"
git submodule update --init

say "Python venv"
[ -d .venv ] || python3 -m venv .venv
.venv/bin/pip install -q -r requirements-dev.txt

say "Dashboard UI dependencies"
[ -d runtime/ui/node_modules ] || (cd runtime/ui && npm ci --silent)

say "Ollama and the akane-router model"
if command -v ollama >/dev/null; then
  ollama pull qwen3:8b
  scripts/build_router.sh
else
  warn "ollama not installed — brew install ollama, then re-run this script."
fi

say "Piper voices"
PIPER=https://huggingface.co/rhasspy/piper-voices/resolve/main/en
mkdir -p models/piper
fetch_voice() {  # $1 = voice name, $2 = path under $PIPER
  for ext in onnx onnx.json; do
    [ -f "models/piper/$1.$ext" ] || curl -fsSL -o "models/piper/$1.$ext" "$PIPER/$2/$1.$ext"
  done
}
# Akane's voice:
fetch_voice en_GB-alba-medium en_GB/alba/medium
# Stand-in for the user's voice when generating wake-word training clips:
fetch_voice en_GB-northern_english_male-medium en_GB/northern_english_male/medium
# The Alba URL in full, for reference:
# https://huggingface.co/rhasspy/piper-voices/resolve/main/en/en_GB/alba/medium/

say "pnd-notes (read-only knowledge base)"
if [ -d ../pnd-notes/node_modules ]; then
  say "pnd-notes already installed"
elif [ -d ../pnd-notes ]; then
  (cd ../pnd-notes && npm ci --silent)
else
  warn "../pnd-notes not found — clone it next to akane for the recall agent."
fi

say "Machine-local config"
[ -f config.local.yaml ] || cp config.local.example.yaml config.local.yaml

say "Data directory"
mkdir -p "$HOME/.akane"

if [ ! -f models/ok_akane.onnx ]; then
  warn "models/ok_akane.onnx missing — copy it from your old machine, or run scripts/train_wakeword.sh"
fi

say "Done. Start with: .venv/bin/python akane.py dev --voice   (in $REPO)"
