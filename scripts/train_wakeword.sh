#!/usr/bin/env bash
# Train the "ok Akane" (uh-KANE) wake-word model → models/ok_akane.onnx.
#
# 1. Generates synthetic clips of wakeword/phrases.yaml into training/ with a
#    male Piper voice (the clips stand in for *you* saying the wake word, so
#    they shouldn't use Akane's own voice).
# 2. Trains openWakeWord on them (~10-20 min on CPU).
#
# Accuracy improves a lot with real recordings of your own voice:
#   .venv/bin/python runtime/scripts/wakeword/record_wakeword_samples.py --count 40
# (its prompts still say "ok Dann" — say "ok Akane" instead), then move the
# clips from runtime/training/positive_real/ to training/positive_real/ and
# re-run this script.
set -euo pipefail
cd "$(dirname "$0")/.."

PY=.venv/bin/python
WAKE=runtime/scripts/wakeword
VOICE=models/piper/en_GB-northern_english_male-medium.onnx

if [ ! -f "$VOICE" ]; then
  echo "Missing $VOICE — run scripts/setup.sh first." >&2
  exit 1
fi

"$PY" "$WAKE/generate_wakeword_samples.py" \
  --phrases-file wakeword/phrases.yaml --out-dir training --voice-model "$VOICE"
"$PY" "$WAKE/train_wakeword.py" \
  --clips-dir training --voice-model "$VOICE" --out-model models/ok_akane.onnx

echo "Trained models/ok_akane.onnx. Say \"ok Akane\" (uh-KANE) after \`akane dev --voice\`."
