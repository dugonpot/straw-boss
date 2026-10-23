"""Joining the straw net from a Claude Code or Codex session.

The straw net is pi-straw-boss's: a live pi-intercom session on a Herdr pane
that carries an `sb_role` token. A Claude Code or Codex main agent joins it by
running pi-straw-boss's `src/agent/cli.ts join`, which starts one detached
sidecar for the pane. This module finds that CLI and the `tsx` loader it needs,
starts the join from the SessionStart hook, and names the commands a session
uses afterwards. It stays optional: without Herdr, pi-straw-boss, pi-intercom,
`tsx`, or `node`, nothing starts and the hook's output is unchanged.
"""

from __future__ import annotations

import os
import shlex
import shutil
import subprocess
from collections.abc import Mapping
from pathlib import Path

from straw_boss.orchestrator import record_path

PACKAGE_NAME = "pi-straw-boss"
CLI_RELATIVE = Path("src") / "agent" / "cli.ts"
KINDS = frozenset({"claude", "codex"})


def agent_directory(env: Mapping[str, str]) -> Path:
    configured = env.get("PI_CODING_AGENT_DIR")
    return Path(configured) if configured else Path.home() / ".pi" / "agent"


def find_package(env: Mapping[str, str] | None = None) -> Path | None:
    """The pi-straw-boss package that has the net CLI, or None.

    A release before the net (no `src/agent/cli.ts`) counts as absent.
    """
    env = os.environ if env is None else env
    named = env.get("STRAW_BOSS_PI_PACKAGE")
    package = Path(named) if named else agent_directory(env) / "npm" / "node_modules" / PACKAGE_NAME
    return package if (package / CLI_RELATIVE).is_file() else None


def find_intercom(package: Path, env: Mapping[str, str]) -> Path | None:
    named = env.get("STRAW_BOSS_INTERCOM")
    candidates = [
        Path(named) if named else None,
        package.parent / "pi-intercom",
        agent_directory(env) / "npm" / "node_modules" / "pi-intercom",
    ]
    for candidate in candidates:
        if candidate is not None and (candidate / "broker" / "client.ts").is_file():
            return candidate
    return None


def find_loader(intercom: Path) -> Path | None:
    """The `tsx` loader pi-intercom starts its own broker with."""
    candidates = [intercom / "node_modules" / "tsx" / "dist" / "loader.mjs"]
    candidates.append(intercom.parent / "tsx" / "dist" / "loader.mjs")
    candidates.extend(
        ancestor / "node_modules" / "tsx" / "dist" / "loader.mjs" for ancestor in intercom.parents
    )
    return next((path for path in candidates if path.is_file()), None)


def node_command(env: Mapping[str, str] | None = None) -> tuple[list[str], str]:
    """`node --import <tsx loader> <cli.ts>` as an argv prefix, or ([], why not)."""
    env = os.environ if env is None else env
    package = find_package(env)
    if package is None:
        return [], (
            f"{PACKAGE_NAME} with the net CLI ({CLI_RELATIVE}) was not found; install a "
            f"{PACKAGE_NAME} release that has it, or name its directory in STRAW_BOSS_PI_PACKAGE"
        )
    intercom = find_intercom(package, env)
    if intercom is None:
        return [], "pi-intercom was not found; install it with pi, or name its directory in STRAW_BOSS_INTERCOM"
    loader = find_loader(intercom)
    if loader is None:
        return [], f"the tsx loader was not found beside {intercom}"
    node = shutil.which("node", path=env.get("PATH"))
    if node is None:
        return [], "node was not found on PATH"
    return [node, "--import", loader.resolve().as_uri(), str(package / CLI_RELATIVE)], ""


def straw_net_script() -> Path:
    return Path(__file__).resolve().parent.parent / "straw-net.py"


def session_record_path(kind: str, session_id: str) -> Path:
    """Where this session's orchestrator record lands once it registers."""
    return record_path(kind, session_id)


def join_argv(prefix: list[str], pane: str, kind: str, session_id: str) -> list[str]:
    return [
        *prefix,
        "join",
        "--pane",
        pane,
        "--kind",
        kind,
        "--session",
        session_id,
        "--record",
        str(session_record_path(kind, session_id)),
        "--cli",
        str(straw_net_script()),
    ]


def start_detached(argv: list[str], env: Mapping[str, str]) -> None:
    options: dict[str, object] = {}
    if os.name == "nt":
        options["creationflags"] = 0x00000008 | 0x00000200  # DETACHED_PROCESS | CREATE_NEW_PROCESS_GROUP
    else:
        options["start_new_session"] = True
    subprocess.Popen(  # noqa: S603 - argv is built from resolved paths only
        argv,
        stdin=subprocess.DEVNULL,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        env=dict(env),
        close_fds=True,
        **options,  # type: ignore[arg-type]
    )


def priming_section() -> str:
    run = f"uv run --script {shlex.quote(str(straw_net_script()))}"
    return (
        "## Straw net\n\n"
        "This session has joined the straw net of its Herdr tab as a member (pi-straw-boss), "
        "so a pi tower, pi sessions, and the Straw Boss GUI can see it and reach it. "
        f"Run these from this pane with `{run}`:\n\n"
        "- `status` shows who the tab's main is and whether a tower is up.\n"
        "- `promote` makes this session the tab's main when the tab has none. "
        "Registering with `register-orchestrator.py --scope …` does it automatically.\n"
        "- `call-tower --message M [--workspace W]` opens the tower if needed and sends it M.\n"
        "- `broadcast --message M [--scope tab|workspace|towers|all]` sends M to the net.\n"
        "- `send --to ID --message M` sends M to one session, which is how you reply.\n"
        "- `rename --name N` changes the name the net shows.\n\n"
        "Net messages arrive in this pane as one `[straw net from=… id=… role=… reply=\"…\"]` line. "
        "Answer one with the `reply` command it carries."
    )


def join_section(session_id: str, kind: str, env: Mapping[str, str] | None = None) -> str | None:
    """Start this session's net join and return the priming section, or None.

    None means the net is not in play (no pane, no pi-straw-boss, an unsupported
    agent), so the hook's output stays what it was. This never raises and never
    waits for the join: session start comes first.
    """
    env = os.environ if env is None else env
    pane = env.get("HERDR_PANE_ID")
    if not pane or not session_id or kind not in KINDS:
        return None
    try:
        prefix, _ = node_command(env)
        if not prefix:
            return None
        start_detached(join_argv(prefix, pane, kind, session_id), env)
    except Exception as exc:  # noqa: BLE001 - the net never costs a session its start
        return f"Straw net: joining failed ({type(exc).__name__}: {exc}); this session stays outside the net."
    return priming_section()
