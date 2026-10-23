#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.11"
# dependencies = []
# ///
"""Talk to the straw net from this pane: status, promote, call-tower, broadcast, send, rename.

Runs pi-straw-boss's net CLI against the sidecar of this Herdr pane and passes
its exit code through: 0 ok, 1 refused or failed (the reason on stderr), 2 no
sidecar, no pi-straw-boss, or a usage error.
"""

from __future__ import annotations

import os
import subprocess
import sys

from straw_boss.net import node_command

USAGE = (
    "usage: straw-net.py status | promote | stop\n"
    "       straw-net.py call-tower --message M [--workspace W]\n"
    "       straw-net.py broadcast --message M [--scope tab|workspace|towers|all]\n"
    "       straw-net.py send --to ID --message M\n"
    "       straw-net.py rename --name N"
)


def main(argv: list[str]) -> int:
    if not argv or argv[0] in {"-h", "--help"}:
        print(USAGE, file=sys.stderr)
        return 2
    command, reason = node_command()
    if not command:
        print(f"straw-net.py: {reason}", file=sys.stderr)
        return 2
    return subprocess.run([*command, *argv], env=os.environ.copy(), check=False).returncode


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
