"""Filesystem layout, ports, and URLs the launcher depends on.

The FastAPI app, UI, and voice pipeline live in the pnd-mcp submodule
(`runtime/`) — this repo only holds persona config (`config.yaml`) and
persona-specific MCP tool-servers on top of that shared runtime. Every child
process is started with `cwd=RUNTIME_DIR` (or `UI_DIR`) so that `app.main:app`
and `npm run dev` resolve inside the submodule.
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from shared.persona import Persona

IS_WINDOWS = sys.platform == "win32"

REPO_ROOT = Path(__file__).resolve().parent.parent
RUNTIME_DIR = REPO_ROOT / "runtime"
UI_DIR = RUNTIME_DIR / "ui"
CONFIG_PATH = REPO_ROOT / "config.yaml"
MODELS_DIR = REPO_ROOT / "models"

# One venv at the repo root serves both this repo and runtime/.
VENV_BIN = REPO_ROOT / ".venv" / ("Scripts" if IS_WINDOWS else "bin")
VENV_UVICORN = VENV_BIN / ("uvicorn.exe" if IS_WINDOWS else "uvicorn")



def load_persona() -> Persona:
    """Akane's identity and ports from config.yaml's `persona:` block (plus
    config.local.yaml), resolved by the runtime's own loader so the launcher
    and the runtime can never disagree. The runtime's defaults apply when
    config.yaml doesn't exist yet."""
    if str(RUNTIME_DIR) not in sys.path:
        sys.path.insert(0, str(RUNTIME_DIR))
    from shared.persona import persona_from_config
    from voice.config import load_config

    cfg = load_config(CONFIG_PATH) if CONFIG_PATH.is_file() else None
    return persona_from_config(cfg)


_PERSONA = load_persona()
PERSONA_NAME = _PERSONA.name
API_PORT = _PERSONA.api_port
UI_PORT = _PERSONA.ui_port


def node_tool(name: str) -> str:
    """Executable name for a Node CLI (`npm`, `npx`) on this platform —
    Windows needs the `.cmd` shim since Popen doesn't go through a shell."""
    return f"{name}.cmd" if IS_WINDOWS else name


def api_health_url(port: int) -> str:
    """The runtime API's health endpoint — returns 200 once it's accepting requests."""
    return f"http://127.0.0.1:{port}/api/v1/health"


def ui_url(port: int) -> str:
    """The Vite dev server's root URL, as opened in a browser/Electron window."""
    return f"http://localhost:{port}"
