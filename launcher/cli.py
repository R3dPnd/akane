"""Command-line interface: parse arguments and dispatch to launcher.commands."""

from __future__ import annotations

import argparse

from launcher import commands

DESCRIPTION = "Developer tooling for Akane: run, stop, and restart Akane."

EPILOG = """\
Saying "goodbye" or "thanks Akane" only ends the current
conversation, not the process — use `stop` or Ctrl+C to actually stop Akane.
`restart` is also available as the dashboard restart button, or by saying
"restart yourself"/"restart Akane". Restarts are always human-triggered."""


def _add_voice_flags(subparser: argparse.ArgumentParser, voice_help: str) -> None:
    group = subparser.add_mutually_exclusive_group()
    group.add_argument("--voice", action="store_true", help=voice_help)
    group.add_argument(
        "--speak",
        action="store_true",
        help="read replies to typed chat aloud, without ever listening (no mic)",
    )


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="akane",
        description=DESCRIPTION,
        epilog=EPILOG,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    subparsers = parser.add_subparsers(dest="command", metavar="<command>")

    dev = subparsers.add_parser(
        "dev",
        aliases=["code"],
        help="dashboard in a browser tab, text only (add --voice or --speak)",
    )
    _add_voice_flags(dev, voice_help="listen for the wake word and speak; opens a fullscreen Electron window")
    dev.set_defaults(run=lambda args: commands.cmd_dev(voice=args.voice, speak=args.speak))

    electron = subparsers.add_parser("electron", help="dashboard in an Electron window with hot reload (add --voice or --speak)")
    _add_voice_flags(electron, voice_help="listen for the wake word and speak")
    electron.set_defaults(run=lambda args: commands.cmd_electron(voice=args.voice, speak=args.speak))

    start = subparsers.add_parser("start", help="voice only, no dashboard UI (API + listening voice pipeline)")
    start.set_defaults(run=lambda args: commands.cmd_start())

    stop = subparsers.add_parser(
        "stop",
        help="stop every running akane process, including orphans from a closed terminal",
    )
    stop.set_defaults(run=lambda args: commands.cmd_stop())

    hunt = subparsers.add_parser("hunt", help="run a job hunt now and write the morning report")
    hunt.set_defaults(run=lambda args: commands.cmd_hunt())

    jobs = subparsers.add_parser("jobs-app", help="run the pnd-job-search app as a background service")
    jobs.add_argument("action", choices=["install", "uninstall", "status", "load-resume"])
    jobs.add_argument("resume", nargs="?", help="path to a .docx (load-resume only)")
    jobs.set_defaults(run=lambda args: commands.cmd_jobs_app(args.action, resume=args.resume))

    restart = subparsers.add_parser("restart", help="stop and relaunch with the same mode/flags")
    restart.set_defaults(run=lambda args: commands.cmd_restart(relaunch=main))

    return parser


def main(argv: list[str]) -> int:
    """Run the `akane` CLI with `argv` (excluding the program name); returns the exit code."""
    parser = build_parser()
    args = parser.parse_args(argv)
    if args.command is None:
        parser.print_help()
        return 0
    return args.run(args)
