"""The nightly job hunt as a launchd job: `akane schedule install|uninstall|status`.

Runs `akane hunt` daily at `job_hunt.run_at` (default 04:00). If the Mac is
asleep then, launchd runs the missed job as soon as it wakes (the user's
choice — no pmset wake schedule). The morning report is delivered later,
when Akane is ready (see the runtime's morning_report_service).
"""

from __future__ import annotations

import os
import plistlib
import re
import subprocess
from pathlib import Path
from typing import Any

from launcher import paths

LABEL = "com.r3dpnd.akane-hunt"
PLIST_PATH = Path.home() / "Library" / "LaunchAgents" / f"{LABEL}.plist"
LOG_DIR = Path.home() / ".akane" / "logs"
DEFAULT_RUN_AT = "04:00"


def parse_run_at(value: str) -> tuple[int, int]:
    match = re.fullmatch(r"(\d{1,2}):(\d{2})", value.strip())
    if not match or int(match[1]) > 23 or int(match[2]) > 59:
        raise ValueError(f"job_hunt.run_at must be HH:MM (24-hour), got {value!r}")
    return int(match[1]), int(match[2])


def run_at() -> str:
    paths.load_persona()  # puts runtime/ on sys.path
    from voice.config import load_config

    cfg = load_config(paths.CONFIG_PATH) if paths.CONFIG_PATH.is_file() else {}
    return str((cfg.get("job_hunt") or {}).get("run_at") or DEFAULT_RUN_AT)


def build_plist(python: Path, akane_py: Path, repo: Path, at: str, path_env: str, log_dir: Path) -> dict[str, Any]:
    hour, minute = parse_run_at(at)
    return {
        "Label": LABEL,
        "ProgramArguments": [str(python), str(akane_py), "hunt"],
        "WorkingDirectory": str(repo),
        "StartCalendarInterval": {"Hour": hour, "Minute": minute},
        "EnvironmentVariables": {"PATH": path_env},  # the hunt calls `claude`
        "RunAtLoad": False,
        "StandardOutPath": str(log_dir / "akane-hunt.log"),
        "StandardErrorPath": str(log_dir / "akane-hunt.log"),
    }


def _path_env() -> str:
    parts = os.environ.get("PATH", "").split(":") + [str(Path.home() / ".local" / "bin"), "/opt/homebrew/bin"]
    return ":".join(dict.fromkeys(p for p in parts if p))


def _launchctl(*args: str) -> subprocess.CompletedProcess:
    return subprocess.run(["launchctl", *args], capture_output=True, text=True)


def cmd_install() -> int:
    at = run_at()
    try:
        plist = build_plist(paths.VENV_BIN / "python", paths.REPO_ROOT / "akane.py", paths.REPO_ROOT,
                            at, _path_env(), LOG_DIR)
    except ValueError as e:
        print(f"[akane] {e} — fix job_hunt.run_at in config.local.yaml", flush=True)
        return 1
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    PLIST_PATH.parent.mkdir(parents=True, exist_ok=True)
    PLIST_PATH.write_bytes(plistlib.dumps(plist))
    domain = f"gui/{os.getuid()}"
    _launchctl("bootout", f"{domain}/{LABEL}")  # fine if it wasn't loaded
    loaded = _launchctl("bootstrap", domain, str(PLIST_PATH))
    if loaded.returncode != 0:
        print(f"[akane] launchctl bootstrap failed: {loaded.stderr.strip()}", flush=True)
        return 1
    print(f"[akane] Job hunt scheduled daily at {at} (runs when the Mac wakes if it was asleep).", flush=True)
    return 0


def cmd_uninstall() -> int:
    _launchctl("bootout", f"gui/{os.getuid()}/{LABEL}")
    PLIST_PATH.unlink(missing_ok=True)
    print("[akane] Nightly job hunt unscheduled.", flush=True)
    return 0


def cmd_status() -> int:
    loaded = _launchctl("print", f"gui/{os.getuid()}/{LABEL}").returncode == 0
    print(f"[akane] nightly hunt: {'loaded' if loaded else 'not loaded'}, runs daily at {run_at()}", flush=True)
    log = LOG_DIR / "akane-hunt.log"
    lines = [line for line in log.read_text().splitlines() if line.strip()] if log.is_file() else []
    if lines:
        print(f"[akane] last run: {lines[-1]}", flush=True)
    return 0 if loaded else 1
