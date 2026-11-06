"""The `akane` CLI launcher: starts, stops, and restarts Akane's API/UI/voice
processes out of the `runtime/` (pnd-mcp) submodule.

`akane.py` at the repo root is the entry point; it only calls `launcher.cli.main`.

Module map:
    paths      Where things live (repo, runtime submodule, venv, ports, URLs).
    readiness  Polling a URL until it serves — "is the API/UI up yet?".
    processes  Building and spawning the API, Vite, and Electron child processes.
    supervisor Owning those children and shutting them down together.
    discovery  Finding akane processes already running on this machine (stop/restart).
    commands   One function per subcommand, composed from the modules above.
    cli        Argument parsing and dispatch.
"""
