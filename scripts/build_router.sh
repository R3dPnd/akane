#!/usr/bin/env bash
# Build (or rebuild) the akane-router Ollama model from models/akane-router.Modelfile.
# Run after editing the Modelfile or pulling a newer qwen2.5:7b-instruct.
set -euo pipefail
cd "$(dirname "$0")/.."
runtime/scripts/wakeword/build_router_model.sh akane-router models/akane-router.Modelfile
