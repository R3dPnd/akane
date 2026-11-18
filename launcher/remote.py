"""Akane's dashboard on the user's other devices: `akane remote on|off|status`.

The API listens on 127.0.0.1 only, so it's never on the open network (home
or café Wi-Fi). `tailscale serve` publishes it at a private HTTPS address
that only devices signed in to the user's tailnet can reach, from anywhere —
no router port forwarding. FastAPI serves the built UI (runtime/ui/dist) on
the same port, so the remote browser gets the dashboard and the API together.
"""

from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path

from launcher import paths

APP_CLI = Path("/Applications/Tailscale.app/Contents/MacOS/Tailscale")
INSTALL_HINT = ("[akane] Tailscale isn't installed. Install it on this Mac and the other computer "
                "(`brew install --cask tailscale`, or tailscale.com/download), sign in to the same "
                "account on both, then run `akane remote on`.")


def tailscale_bin() -> str | None:
    found = shutil.which("tailscale")
    if found:
        return found
    return str(APP_CLI) if APP_CLI.is_file() else None


def ui_is_stale(ui_dir: Path) -> bool:
    """True when ui/dist is missing or older than any file under ui/src."""
    built = ui_dir / "dist" / "index.html"
    if not built.is_file():
        return True
    newest = max((p.stat().st_mtime for p in (ui_dir / "src").rglob("*") if p.is_file()), default=0)
    return newest > built.stat().st_mtime


def _run(*argv: str, cwd: Path | None = None) -> subprocess.CompletedProcess:
    return subprocess.run(list(argv), capture_output=True, text=True, cwd=cwd)


def _address(ts: str) -> str | None:
    """The tailnet HTTPS address, or None when Tailscale isn't signed in."""
    status = json.loads(_run(ts, "status", "--json").stdout or "{}")
    dns = (status.get("Self") or {}).get("DNSName", "").rstrip(".")
    return f"https://{dns}/" if status.get("BackendState") == "Running" and dns else None


def cmd_on() -> int:
    ts = tailscale_bin()
    if not ts:
        print(INSTALL_HINT, flush=True)
        return 1
    address = _address(ts)
    if not address:
        print("[akane] Tailscale isn't signed in — run `tailscale up` (or open the Tailscale app), "
              "then `akane remote on` again.", flush=True)
        return 1
    if ui_is_stale(paths.UI_DIR):
        print("[akane] Building the dashboard for remote use…", flush=True)
        built = _run(paths.node_tool("npm"), "run", "build", cwd=paths.UI_DIR)
        if built.returncode != 0:
            print(f"[akane] Dashboard build failed:\n{(built.stderr or built.stdout).strip()}", flush=True)
            return 1
    served = _run(ts, "serve", "--bg", f"http://127.0.0.1:{paths.API_PORT}")
    if served.returncode != 0:
        print(f"[akane] tailscale serve failed: {(served.stderr or served.stdout).strip()}", flush=True)
        return 1
    print(f"[akane] Akane is on your tailnet at {address} — open it on any device signed in to "
          f"your Tailscale account. (It works while Akane is running.)", flush=True)
    return 0


def cmd_off() -> int:
    ts = tailscale_bin()
    if not ts:
        print(INSTALL_HINT, flush=True)
        return 1
    _run(ts, "serve", "--https=443", "off")
    print("[akane] Remote access is off.", flush=True)
    return 0


def cmd_status() -> int:
    ts = tailscale_bin()
    if not ts:
        print(INSTALL_HINT, flush=True)
        return 1
    result = _run(ts, "serve", "status")
    print((result.stdout or result.stderr).strip() or "[akane] Remote access is off.", flush=True)
    return 0
