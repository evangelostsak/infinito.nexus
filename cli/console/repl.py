"""Interactive REPL that forwards each input line to ``python -m cli`` on the host.

Ctrl+C only cancels the current input; the console exits on ``exit``/``quit`` or EOF (Ctrl+D).
Ctrl+Shift+C is intercepted by the terminal emulator (copy shortcut) and never reaches the app.
"""

from __future__ import annotations

import contextlib
import shlex
import signal
import subprocess
import sys

from cli.core.colors import Fore, Style, color_text

with contextlib.suppress(ImportError):
    import readline  # noqa: F401

PROMPT = "infinito> "
WEB_URL = "https://infinito.nexus"
DOCS_URL = "https://docs.infinito.nexus"
LICENSE_NAME = "Infinito.Nexus Community License (Non-Commercial)"
LICENSE_URL = "https://s.infinito.nexus/license"
AUTHOR = "Kevin Veen-Birkenbach"
AUTHOR_URL = "https://cybermaster.space"
EXIT_TOKENS = frozenset({"exit", "quit", ":q"})
STRIPPABLE_PREFIXES = ("infinito", "cli")
HELP_ALIASES = frozenset({"help", "?", "h"})


def _normalize(argv: list[str]) -> list[str]:
    if argv and argv[0] in STRIPPABLE_PREFIXES:
        argv = argv[1:]
    if not argv:
        return ["--help"]
    if argv[0] in HELP_ALIASES:
        return ["--help", *argv[1:]]
    return argv


def _run_cli(argv: list[str]) -> int:
    prev_handler = signal.signal(signal.SIGINT, signal.SIG_IGN)
    try:
        return subprocess.run(
            [sys.executable, "-m", "cli", *argv], check=False
        ).returncode
    finally:
        signal.signal(signal.SIGINT, prev_handler)


def _print_banner() -> None:
    print(color_text("infinito.nexus console 🦫🖥️", Fore.CYAN + Style.BRIGHT))
    print(
        color_text(
            "Type 'exit', 'quit', or Ctrl+D to leave. Ctrl+C cancels the current line.",
            Style.DIM,
        )
    )
    print()
    print(color_text("  Help:    type 'help' or '<command> --help'", Fore.YELLOW))
    print(color_text(f"  Web:     {WEB_URL}", Fore.YELLOW))
    print(color_text(f"  Docs:    {DOCS_URL}", Fore.YELLOW))
    print(color_text(f"  Author:  {AUTHOR} — {AUTHOR_URL}", Style.DIM))
    print(
        color_text(
            f"  License: {LICENSE_NAME} — {LICENSE_URL}",
            Style.DIM,
        )
    )
    print()


def main() -> int:
    _print_banner()
    while True:
        try:
            line = input(PROMPT)
        except KeyboardInterrupt:
            print()
            continue
        except EOFError:
            print()
            return 0

        stripped = line.strip()
        if not stripped:
            continue
        if stripped in EXIT_TOKENS:
            return 0

        try:
            argv = shlex.split(stripped)
        except ValueError as exc:
            print(f"console: parse error: {exc}", file=sys.stderr)
            continue

        _run_cli(_normalize(argv))


if __name__ == "__main__":
    raise SystemExit(main())
