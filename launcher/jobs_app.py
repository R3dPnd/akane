"""Run pnd-job-search (the user's job-hunting app) as an always-on launchd
agent, so the overnight hunt and Akane can reach its API without anyone
starting it. `akane jobs-app install|uninstall|status|load-resume`.

The app lives next to akane (config.yaml `job_search.app_dir`, relative to
runtime/ like every config path). Its `.env` holds the user's JSearch key;
this module only ever adds or replaces the lines it owns and never prints the
key.
"""

from __future__ import annotations

import os
import plistlib
import subprocess
import time
from pathlib import Path
from typing import Any

import requests

from launcher import paths

LABEL = "com.r3dpnd.pnd-job-search"
PLIST_PATH = Path.home() / "Library" / "LaunchAgents" / f"{LABEL}.plist"
LOG_DIR = Path.home() / ".akane" / "logs"
_PLACEHOLDER_PREFIX = "your_"


def _job_search_cfg() -> dict[str, Any]:
    paths.load_persona()  # puts runtime/ on sys.path
    from voice.config import load_config

    cfg = load_config(paths.CONFIG_PATH) if paths.CONFIG_PATH.is_file() else {}
    return cfg.get("job_search") or {}


def app_dir() -> Path:
    return (paths.RUNTIME_DIR / _job_search_cfg().get("app_dir", "../../pnd-job-search")).resolve()


def base_url() -> str:
    return _job_search_cfg().get("base_url", "http://localhost:8080/api/v1").rstrip("/")


def healthy() -> bool:
    try:
        return requests.get(f"{base_url()}/health", timeout=2).status_code == 200
    except requests.RequestException:
        return False


def wait_healthy(timeout: float) -> bool:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if healthy():
            return True
        time.sleep(0.5)
    return False


def build_plist(binary: Path, workdir: Path, path_env: str, log_dir: Path) -> dict[str, Any]:
    return {
        "Label": LABEL,
        "ProgramArguments": [str(binary)],
        "WorkingDirectory": str(workdir),  # the app loads ../.env relative to backend/
        "EnvironmentVariables": {"PATH": path_env},  # `claude` must be findable
        "RunAtLoad": True,
        "KeepAlive": True,
        "StandardOutPath": str(log_dir / "pnd-job-search.log"),
        "StandardErrorPath": str(log_dir / "pnd-job-search.log"),
    }


def merge_env(existing: str, owned: dict[str, str]) -> str:
    """`existing` .env text with `owned` keys replaced in place or appended;
    every other line (the user's JSearch key, comments) is left as is."""
    remaining = dict(owned)
    lines = []
    for line in existing.splitlines():
        key = line.split("=", 1)[0].strip() if "=" in line and not line.lstrip().startswith("#") else None
        if key in remaining:
            lines.append(f"{key}={remaining.pop(key)}")
        else:
            lines.append(line)
    lines += [f"{k}={v}" for k, v in remaining.items()]
    return "\n".join(lines) + "\n"


def _env_path() -> Path:
    return app_dir() / ".env"


def _key_is_set() -> bool:
    env = _env_path().read_text() if _env_path().is_file() else ""
    for line in env.splitlines():
        if line.startswith("JOBS_API_KEY="):
            value = line.split("=", 1)[1].strip()
            return bool(value) and not value.startswith(_PLACEHOLDER_PREFIX)
    return False


def _path_env() -> str:
    parts = os.environ.get("PATH", "").split(":") + [str(Path.home() / ".local" / "bin"), "/opt/homebrew/bin"]
    return ":".join(dict.fromkeys(p for p in parts if p))


def _launchctl(*args: str) -> subprocess.CompletedProcess:
    return subprocess.run(["launchctl", *args], capture_output=True, text=True)


def cmd_install() -> int:
    app, backend = app_dir(), app_dir() / "backend"
    build = subprocess.run(["go", "build", "-o", "bin/pnd-job-search", "."], cwd=backend,
                           capture_output=True, text=True)
    if build.returncode != 0:
        print(f"[akane] pnd-job-search build failed:\n{build.stderr}", flush=True)
        return 1

    env_path = _env_path()
    owned = {
        "DATABASE_URL": f"postgres://{os.environ.get('USER', 'postgres')}@localhost:5432/job_search?sslmode=disable",
        "PORT": "8080",
        "UPLOADS_DIR": str(app / "uploads"),
        "FRONTEND_ORIGIN": "http://localhost:5173",
    }
    env_path.write_text(merge_env(env_path.read_text() if env_path.is_file() else "", owned))

    LOG_DIR.mkdir(parents=True, exist_ok=True)
    PLIST_PATH.parent.mkdir(parents=True, exist_ok=True)
    PLIST_PATH.write_bytes(plistlib.dumps(build_plist(backend / "bin" / "pnd-job-search", backend, _path_env(), LOG_DIR)))
    domain = f"gui/{os.getuid()}"
    _launchctl("bootout", f"{domain}/{LABEL}")  # fine if it wasn't loaded
    loaded = _launchctl("bootstrap", domain, str(PLIST_PATH))
    if loaded.returncode != 0:
        print(f"[akane] launchctl bootstrap failed: {loaded.stderr.strip()}", flush=True)
        return 1
    if not wait_healthy(15):
        print(f"[akane] pnd-job-search didn't answer at {base_url()}/health — see {LOG_DIR / 'pnd-job-search.log'}", flush=True)
        return 1
    print(f"[akane] pnd-job-search running at {base_url()} (JOBS_API_KEY: {'set' if _key_is_set() else 'not set'})", flush=True)
    return 0


def cmd_uninstall() -> int:
    _launchctl("bootout", f"gui/{os.getuid()}/{LABEL}")
    PLIST_PATH.unlink(missing_ok=True)
    print("[akane] pnd-job-search agent removed.", flush=True)
    return 0


def cmd_status() -> int:
    loaded = _launchctl("print", f"gui/{os.getuid()}/{LABEL}").returncode == 0
    up = healthy()
    print(f"[akane] launchd agent: {'loaded' if loaded else 'not loaded'}", flush=True)
    print(f"[akane] API {base_url()}: {'healthy' if up else 'not answering'}", flush=True)
    print(f"[akane] JOBS_API_KEY: {'set' if _key_is_set() else 'not set'}", flush=True)
    return 0 if up else 1


def cmd_load_resume(path: Path) -> int:
    if not path.is_file():
        print(f"[akane] resume not found: {path}", flush=True)
        return 1
    with path.open("rb") as f:
        created = requests.post(f"{base_url()}/resumes", data={"label": "Base resume"},
                                files={"file": (path.name, f)}, timeout=60)
    if created.status_code not in (200, 201):
        print(f"[akane] upload failed ({created.status_code})", flush=True)
        return 1
    resume_id = created.json()["id"]
    activated = requests.post(f"{base_url()}/resumes/{resume_id}/activate", timeout=30)
    if activated.status_code != 200:
        print(f"[akane] activate failed ({activated.status_code})", flush=True)
        return 1
    print(f"[akane] {path.name} uploaded and active (id {resume_id}).", flush=True)
    return 0
