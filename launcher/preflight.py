"""Checks run before Akane starts, so a fresh machine or a busy port
gets a one-line explanation and the command that fixes it, instead of a
uvicorn traceback or a voice pipeline that silently never wakes.

Paths in config.yaml are relative to runtime/ (every child process runs
there), so they're resolved against paths.RUNTIME_DIR here too.
"""

from __future__ import annotations

import socket
import subprocess
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal

from launcher import paths


@dataclass(frozen=True)
class Problem:
    level: Literal["error", "warning"]
    message: str
    fix: str


def _resolve(value: str) -> Path:
    return (paths.RUNTIME_DIR / value).resolve()


def _check_wake_model(config: dict[str, Any]) -> list[Problem]:
    model = (config.get("wake_word") or {}).get("model") or ""
    # A bare name (hey_jarvis, alexa, ...) is an openWakeWord built-in, not a file.
    if not model.endswith(".onnx") or _resolve(model).is_file():
        return []
    return [Problem("error", f"wake-word model {Path(model).name} not found",
                    "copy it from your old machine into models/, or run scripts/train_wakeword.sh")]


def _check_voice_model(config: dict[str, Any]) -> list[Problem]:
    voice = (config.get("tts") or {}).get("voice_model")
    if not voice:
        return []
    onnx = _resolve(voice if voice.endswith(".onnx") else voice + ".onnx")
    if onnx.is_file():
        return []
    return [Problem("error", f"Piper voice {onnx.stem} not found", "run scripts/setup.sh to download it")]


def _check_router(config: dict[str, Any], models: list[str] | None) -> list[Problem]:
    if models is None:
        return [Problem("warning", "ollama is not installed — Akane has no local model to answer with",
                        "brew install ollama, then run scripts/setup.sh")]
    wanted = (config.get("ollama") or {}).get("model")
    if not wanted or wanted in models or f"{wanted}:latest" in models:
        return []
    return [Problem("warning", f"Ollama model {wanted} is not built", "run scripts/build_router.sh")]


def _check_node_servers(config: dict[str, Any]) -> list[Problem]:
    problems = []
    for server in (config.get("mcp") or {}).get("servers") or []:
        scripts = [a for a in server.get("args") or [] if a.endswith((".mjs", ".js"))]
        for script in scripts:
            if not _resolve(script).is_file():
                problems.append(Problem(
                    "warning", f"MCP server {server.get('name')} is unavailable ({script} not found)",
                    "git clone the repo it lives in next to akane (e.g. ~/Git/r3dpnd/), then run scripts/setup.sh"))
    return problems


def _check_electron() -> list[Problem]:
    if (paths.RUNTIME_DIR / "ui" / "node_modules" / "electron" / "path.txt").is_file():
        return []
    return [Problem("error", "Electron isn't installed correctly, so the app window can't open",
                    "run scripts/fix_electron.sh")]


def check(
    voice: bool,
    *,
    speak: bool = False,
    electron: bool = False,
    config: dict[str, Any],
    ports: list[int],
    port_in_use: Callable[[int], bool],
    ollama_models: Callable[[], list[str] | None],
) -> list[Problem]:
    """Everything wrong with this machine for starting Akane, errors first."""
    problems = [
        Problem("error", f"port {port} is already in use by another program",
                f"run `akane stop`; if it's still busy, `lsof -i :{port}` shows what's using it")
        for port in ports if port_in_use(port)
    ]
    if voice:
        problems += _check_wake_model(config)
    if voice or speak:
        problems += _check_voice_model(config)
    if electron:
        problems += _check_electron()
    problems += _check_router(config, ollama_models()) + _check_node_servers(config)
    return problems


def report(problems: list[Problem]) -> bool:
    """Print each problem; True when nothing blocks startup (warnings only)."""
    for p in problems:
        colour = "\033[31m" if p.level == "error" else "\033[33m"
        print(f"{colour}[akane] {p.level}: {p.message} — fix: {p.fix}\033[0m", flush=True)
    return not any(p.level == "error" for p in problems)


def port_in_use(port: int) -> bool:
    """Whether something is listening on `port` on this machine (IPv4 or IPv6).

    Connects rather than test-binding: a bind fails for a minute after any
    server stops (its closed connections sit in TIME_WAIT) even though
    uvicorn/Vite would start fine, and a bind to 127.0.0.1 can't see Vite
    listening on [::1] only.
    """
    for host in ("127.0.0.1", "::1"):
        try:
            with socket.create_connection((host, port), timeout=0.5):
                return True
        except OSError:
            continue
    return False


def ollama_models() -> list[str] | None:
    """Model names from `ollama list`, or None when ollama isn't installed."""
    try:
        out = subprocess.run(["ollama", "list"], capture_output=True, text=True, timeout=10).stdout
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return None
    return [line.split()[0] for line in out.splitlines()[1:] if line.strip()]


def _load_config() -> dict[str, Any]:
    if not paths.CONFIG_PATH.is_file():
        return {}
    paths.load_persona()  # puts runtime/ on sys.path
    from voice.config import load_config

    return load_config(paths.CONFIG_PATH)


def run(voice: bool, ui: bool, speak: bool = False, electron: bool = False) -> bool:
    """Check this machine with the real probes and report; False means don't start."""
    ports = [paths.API_PORT, paths.UI_PORT] if ui else [paths.API_PORT]
    problems = check(voice, speak=speak, electron=electron, config=_load_config(), ports=ports,
                     port_in_use=port_in_use, ollama_models=ollama_models)
    return report(problems)
