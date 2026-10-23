from __future__ import annotations

import json
import os
import stat
import subprocess
import sys
import time
import unittest
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

from straw_boss import net
from straw_boss.orchestrator import record_path
from tests.dispatched_agent_lifecycle_support import ROOT, SCRIPTS, DispatchedAgentLifecycleFixture

FAKE_NODE = """#!/bin/sh
if [ -n "$FAKE_NODE_OUT" ]; then
  : > "$FAKE_NODE_OUT.tmp"
  for arg in "$@"; do printf '%s\\n' "$arg" >> "$FAKE_NODE_OUT.tmp"; done
  printf 'pane=%s\\n' "$HERDR_PANE_ID" >> "$FAKE_NODE_OUT.tmp"
  mv "$FAKE_NODE_OUT.tmp" "$FAKE_NODE_OUT"
fi
exit ${FAKE_NODE_EXIT:-0}
"""


class StrawNetTests(DispatchedAgentLifecycleFixture, unittest.TestCase):
    def setUp(self) -> None:
        super().setUp()
        self.package = self.home / "pkg" / "pi-straw-boss"
        (self.package / "src" / "agent").mkdir(parents=True)
        (self.package / "src" / "agent" / "cli.ts").write_text("// fake\n")
        self.intercom = self.home / "pkg" / "pi-intercom"
        (self.intercom / "broker").mkdir(parents=True)
        (self.intercom / "broker" / "client.ts").write_text("// fake\n")
        self.loader = self.home / "pkg" / "tsx" / "dist" / "loader.mjs"
        self.loader.parent.mkdir(parents=True)
        self.loader.write_text("// fake\n")
        self.bin = self.home / "bin"
        self.bin.mkdir()
        node = self.bin / "node"
        node.write_text(FAKE_NODE)
        node.chmod(node.stat().st_mode | stat.S_IXUSR)
        self.out = self.home / "node-argv.txt"

    def env(self, **extra: str) -> dict[str, str]:
        env = {
            **os.environ,
            "HOME": str(self.home),
            "PATH": f"{self.bin}{os.pathsep}{os.environ['PATH']}",
            "FAKE_NODE_OUT": str(self.out),
            "STRAW_BOSS_PI_PACKAGE": str(self.package),
            "STRAW_BOSS_INTERCOM": str(self.intercom),
            "PI_CODING_AGENT_DIR": str(self.home / "agent"),
            "HERDR_PANE_ID": "p9",
        }
        env.pop("STRAW_BOSS_RECORD", None)
        for key, value in extra.items():
            if value == "":
                env.pop(key, None)
            else:
                env[key] = value
        return env

    def hook(self, payload: dict[str, Any], **extra: str) -> subprocess.CompletedProcess[str]:
        result = subprocess.run(
            [sys.executable, str(SCRIPTS / "orchestrator-priming.py")],
            input=json.dumps(payload),
            cwd=ROOT,
            env=self.env(**extra),
            capture_output=True,
            text=True,
            timeout=20,
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        return result

    def spawned(self) -> list[str] | None:
        deadline = time.monotonic() + 5
        while time.monotonic() < deadline:
            if self.out.exists():
                return self.out.read_text().splitlines()
            time.sleep(0.05)
        return None

    def assert_nothing_spawned(self) -> None:
        time.sleep(0.4)
        self.assertFalse(self.out.exists())

    def baseline(self, payload: dict[str, Any]) -> str:
        """Today's output: the same hook with no pi-straw-boss to find."""
        return self.hook(payload, STRAW_BOSS_PI_PACKAGE=str(self.home / "absent")).stdout

    # --- silent skips ---

    def test_without_a_herdr_pane_the_output_is_unchanged_and_nothing_spawns(self) -> None:
        payload = {"session_id": "s1", "source": "startup"}
        no_pane = self.hook(payload, HERDR_PANE_ID="").stdout
        self.assertEqual(no_pane, self.baseline(payload))
        self.assertNotIn("Straw net", no_pane)
        self.assert_nothing_spawned()

    def test_without_the_package_the_output_is_byte_identical_and_nothing_spawns(self) -> None:
        payload = {"session_id": "s1", "source": "startup"}
        absent = self.hook(payload, STRAW_BOSS_PI_PACKAGE=str(self.home / "absent")).stdout
        self.assertNotIn("Straw net", absent)
        self.assert_nothing_spawned()
        # A package without src/agent/cli.ts (pi-straw-boss before the net) counts as absent.
        (self.package / "src" / "agent" / "cli.ts").unlink()
        old = self.hook(payload).stdout
        self.assertEqual(old, absent)
        self.assert_nothing_spawned()

    def test_without_the_tsx_loader_or_node_nothing_spawns(self) -> None:
        payload = {"session_id": "s1", "source": "startup"}
        self.loader.unlink()
        self.assertNotIn("Straw net", self.hook(payload).stdout)
        self.assert_nothing_spawned()

    def test_a_dispatched_session_never_joins(self) -> None:
        contract = self.home / "contract.md"
        contract.write_text("You are a dispatched worker.\n")
        instruction = self.home / ".straw-boss" / "dispatch" / "one.json"
        instruction.write_text(json.dumps({"session_id": "worker-1", "contract_path": str(contract)}))
        result = self.hook({"session_id": "worker-1", "source": "resume"})
        self.assertIn("dispatched worker", result.stdout)
        self.assertNotIn("Straw net", result.stdout)
        self.assert_nothing_spawned()

    def test_an_antigravity_payload_never_joins(self) -> None:
        payload = {"conversationId": "agy-1", "source": "startup"}
        result = self.hook(payload)
        self.assertNotIn("Straw net", result.stdout)
        self.assert_nothing_spawned()

    # --- joining ---

    def test_a_fresh_claude_session_spawns_join_with_its_record(self) -> None:
        result = self.hook({"session_id": "claude-sess-1", "source": "startup"})
        self.assertIn("Straw net", result.stdout)
        argv = self.spawned()
        self.assertIsNotNone(argv)
        assert argv is not None
        self.assertEqual(argv[0], "--import")
        self.assertTrue(argv[1].startswith("file://"))
        self.assertTrue(argv[1].endswith("/tsx/dist/loader.mjs"))
        self.assertEqual(argv[2], str(self.package / "src" / "agent" / "cli.ts"))
        rest = argv[3:]
        self.assertEqual(rest[0], "join")
        flags = dict(zip(rest[1:-1:2], rest[2::2], strict=True))
        self.assertEqual(flags["--pane"], "p9")
        self.assertEqual(flags["--kind"], "claude")
        self.assertEqual(flags["--session"], "claude-sess-1")
        expected_record = self.home / ".straw-boss" / "orchestrators" / "claude-claude-sess-1.json"
        self.assertEqual(flags["--record"], str(expected_record))
        self.assertEqual(flags["--cli"], str(SCRIPTS / "straw-net.py"))
        self.assertEqual(argv[-1], "pane=p9")
        self.assertIn(str(SCRIPTS / "straw-net.py"), result.stdout)

    def test_a_codex_rollout_session_spawns_join_as_codex(self) -> None:
        transcript = self.home / "rollout-2026-abc.jsonl"
        transcript.write_text("")
        payload = {"session_id": "codex-sess-1", "source": "startup", "transcript_path": str(transcript)}
        self.hook(payload)
        argv = self.spawned()
        assert argv is not None
        flags = dict(zip(argv[4:-1:2], argv[5::2], strict=True))
        self.assertEqual(flags["--kind"], "codex")
        self.assertEqual(flags["--session"], "codex-sess-1")

    def test_a_renewed_main_agent_joins_but_a_renewed_worker_does_not(self) -> None:
        records = self.home / ".straw-boss" / "renewal"
        records.mkdir(parents=True)
        record = {
            "pane_id": "p9",
            "agent_kind": "claude",
            "session_id": "old-session",
            "role": "main-agent",
            "payload": "Next action: continue.",
            "instruction_paths": [],
            "status": "pending",
        }
        (records / "pane-p9.json").write_text(json.dumps(record))
        result = self.hook({"session_id": "renewed-1", "source": "clear"})
        self.assertIn("Next action: continue.", result.stdout)
        self.assertIn("Straw net", result.stdout)
        argv = self.spawned()
        assert argv is not None
        self.assertIn("renewed-1", argv)

        self.out.unlink()
        (records / "pane-p9.json").write_text(json.dumps({**record, "role": "standalone-worker"}))
        worker = self.hook({"session_id": "renewed-2", "source": "clear"})
        self.assertNotIn("Straw net", worker.stdout)
        self.assert_nothing_spawned()

    def test_the_section_is_appended_after_the_unchanged_stance(self) -> None:
        payload = {"session_id": "s1", "source": "startup"}
        plain = self.baseline(payload)
        with_net = self.hook(payload).stdout
        self.assertTrue(with_net.startswith(plain.rstrip("\n")))
        self.assertIn("[straw net", with_net.removeprefix(plain.rstrip("\n")))

    def test_a_failing_spawn_never_fails_the_hook(self) -> None:
        # No node anywhere on PATH: the section must not claim a join happened.
        payload = {"session_id": "s1", "source": "startup"}
        empty = self.home / "nobin"
        empty.mkdir()
        result = self.hook(payload, PATH=str(empty))
        self.assertNotIn("Straw net", result.stdout)

    def test_join_returns_at_once_while_the_child_keeps_running(self) -> None:
        (self.bin / "node").write_text("#!/bin/sh\nsleep 30\n")
        started = time.monotonic()
        result = self.hook({"session_id": "s1", "source": "startup"})
        self.assertLess(time.monotonic() - started, 5)
        self.assertIn("Straw net", result.stdout)

    # --- resolution helpers ---

    def test_package_dir_defaults_to_the_agent_directory(self) -> None:
        agent = self.home / "agent"
        found = agent / "npm" / "node_modules" / "pi-straw-boss"
        (found / "src" / "agent").mkdir(parents=True)
        (found / "src" / "agent" / "cli.ts").write_text("//\n")
        env = {"PI_CODING_AGENT_DIR": str(agent)}
        self.assertEqual(net.find_package(env), found)
        self.assertIsNone(net.find_package({"PI_CODING_AGENT_DIR": str(self.home / "none")}))


class RecordPathAgreement(unittest.TestCase):
    def test_join_record_matches_the_orchestrator_directory(self) -> None:
        self.assertEqual(net.session_record_path("claude", "abc"), record_path("claude", "abc"))


if __name__ == "__main__":
    unittest.main()
