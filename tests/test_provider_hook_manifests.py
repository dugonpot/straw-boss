"""Provider hook discovery must preserve commands and Claude function modules."""
import json
import os
import runpy
from pathlib import Path
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]


def codex_hooks():
    manifest = json.loads((ROOT / '.codex-plugin/plugin.json').read_text())
    return json.loads((ROOT / manifest.get('hooks', 'hooks/hooks.json')).read_text())


class ProviderHookManifestsTest(unittest.TestCase):
    def test_windows_commands_match_readable_generator(self):
        generator = runpy.run_path(str(ROOT / 'scripts/sync-codex-windows-hooks.py'))
        hooks = [hook for entries in codex_hooks()['hooks'].values()
                 for entry in entries for hook in entry['hooks']]
        for hook, name in zip(hooks, generator['SCRIPTS'], strict=True):
            self.assertEqual(hook['commandWindows'], generator['windows_command'](name))

    def test_codex_discovered_file_uses_supported_top_level_fields(self):
        # Codex 0.155.1 rejects the entire file on unknown fields, including modules.
        payload = codex_hooks()
        self.assertEqual(set(payload) - {'description', 'hooks'}, set())
        self.assertEqual(set(payload['hooks']), {'SessionStart', 'Stop'})

    def test_provider_commands_stay_in_sync_and_claude_keeps_jev(self):
        claude = json.loads((ROOT / 'hooks/hooks.json').read_text())
        # Only Claude's hook input names the subagent making a tool call.
        shared = {event: entries for event, entries in claude['hooks'].items()
                  if event != 'PreToolUse'}
        codex = codex_hooks()['hooks']
        for entries in codex.values():
            for entry in entries:
                for hook in entry['hooks']:
                    self.assertTrue(hook.pop('commandWindows').startswith('powershell.exe '))
        self.assertEqual(codex, shared)
        self.assertEqual(claude['modules'], ['./jev-pruning.ts'])
        self.assertTrue((ROOT / 'hooks' / claude['modules'][0]).is_file())

    @unittest.skipIf(os.name == 'nt', 'POSIX command uses a POSIX shell')
    def test_codex_commands_run_from_installed_root_with_spaces(self):
        # Codex supplies CLAUDE_PLUGIN_ROOT as its compatibility environment.
        with tempfile.TemporaryDirectory(prefix='installed plugin ') as directory:
            root = Path(directory)
            scripts = root / 'scripts'
            scripts.mkdir()
            names = ['orchestrator-priming.py', 'dispatched-agent-stop-guard.py',
                     'context-renewal-guard.py']
            for name in names:
                script = scripts / name
                script.write_text('#!/bin/sh\ncat >/dev/null\nprintf "%s\\n" "' + name + '"\n')
                script.chmod(0o755)
            env = {**os.environ, 'CLAUDE_PLUGIN_ROOT': str(root)}
            seen = []
            for entries in codex_hooks()['hooks'].values():
                for entry in entries:
                    for hook in entry['hooks']:
                        result = subprocess.run(hook['command'], shell=True, input='{}',
                                                text=True, capture_output=True, env=env,
                                                cwd='/', timeout=10)
                        self.assertEqual(result.returncode, 0, result.stderr)
                        seen.append(result.stdout.strip())
            self.assertEqual(seen, names)

    @unittest.skipUnless(os.name == 'nt', 'native Windows command override')
    def test_windows_commands_preserve_input_output_exit_and_root_fallbacks(self):
        with tempfile.TemporaryDirectory(prefix='installed plugin ') as directory:
            root = Path(directory)
            scripts = root / 'scripts'
            scripts.mkdir()
            hooks = [hook for entries in codex_hooks()['hooks'].values()
                     for entry in entries for hook in entry['hooks']]
            names = ['orchestrator-priming.py', 'dispatched-agent-stop-guard.py',
                     'context-renewal-guard.py']
            for name in names:
                (scripts / name).write_text(
                    'import sys\nprint(sys.stdin.read())\n'
                    'print("guard diagnostic", file=sys.stderr)\nsys.exit(2)\n')
            for variable in ['CLAUDE_PLUGIN_ROOT', 'STRAW_BOSS_PLUGIN_ROOT']:
                env = {**os.environ, 'CLAUDE_PLUGIN_ROOT': str(root / 'missing'),
                       'STRAW_BOSS_PLUGIN_ROOT': str(root / 'missing'), variable: str(root)}
                for hook in hooks:
                    result = subprocess.run(hook['commandWindows'], shell=True,
                                            input=json.dumps({'marker': '\u4e2d\u6587 hook input'}), text=True,
                                            capture_output=True, env=env, cwd=directory,
                                            timeout=30)
                    self.assertEqual(result.returncode, 2, result.stderr)
                    self.assertEqual(json.loads(result.stdout), {'marker': '\u4e2d\u6587 hook input'})
                    self.assertIn('guard diagnostic', result.stderr)

    @unittest.skipUnless(os.name == 'nt', 'native Windows command override')
    def test_windows_missing_roots_report_skip(self):
        with tempfile.TemporaryDirectory() as directory:
            env = {**os.environ, 'CLAUDE_PLUGIN_ROOT': '', 'STRAW_BOSS_PLUGIN_ROOT': '',
                   'USERPROFILE': directory}
            for entries in codex_hooks()['hooks'].values():
                for entry in entries:
                    for hook in entry['hooks']:
                        result = subprocess.run(hook['commandWindows'], shell=True,
                                                input='{}', text=True, capture_output=True,
                                                env=env, timeout=15)
                        self.assertEqual(result.returncode, 0, result.stderr)
                        self.assertIn('hook skipped', json.loads(result.stdout)['systemMessage'])

    @unittest.skipUnless(os.name == 'nt', 'native PowerShell parent shell')
    def test_windows_overrides_survive_powershell_parent(self):
        with tempfile.TemporaryDirectory(prefix='installed plugin ') as directory:
            root = Path(directory)
            (root / 'scripts').mkdir()
            for name in ['orchestrator-priming.py', 'dispatched-agent-stop-guard.py',
                         'context-renewal-guard.py']:
                (root / 'scripts' / name).write_text(
                    'import sys\nprint(sys.stdin.read())\nsys.exit(2)\n')
            env = {**os.environ, 'CLAUDE_PLUGIN_ROOT': directory}
            for entries in codex_hooks()['hooks'].values():
                for entry in entries:
                    for hook in entry['hooks']:
                        result = subprocess.run(
                            ['powershell.exe', '-NoProfile', '-NonInteractive', '-Command',
                             hook['commandWindows']], input='{"marker":"outer shell"}',
                            text=True, capture_output=True, env=env, timeout=30)
                        # PowerShell's outer -Command normalizes native failures
                        # to 1; the override must still run and preserve its output.
                        self.assertNotEqual(result.returncode, 0, result.stderr)
                        self.assertEqual(json.loads(result.stdout), {'marker': 'outer shell'})

    @unittest.skipUnless(os.name == 'nt', 'native Windows real guard integration')
    def test_windows_real_guards_accept_codex_rollout(self):
        with tempfile.TemporaryDirectory(prefix='hook home ') as directory:
            home = Path(directory)
            transcript = home / 'rollout-test.jsonl'
            transcript.write_text(json.dumps({'type': 'event_msg', 'payload': {
                'type': 'token_count', 'info': {'last_token_usage': {
                    'input_tokens': 100, 'output_tokens': 5, 'total_tokens': 105}}}}) + '\n')
            env = {**os.environ, 'USERPROFILE': directory, 'HOME': directory,
                   'CLAUDE_PLUGIN_ROOT': str(ROOT), 'STRAW_BOSS_JEV': '0'}
            env.pop('HERDR_PANE_ID', None)
            payload = json.dumps({'session_id': 'windows-hook-test',
                                  'cwd': directory, 'transcript_path': str(transcript)})
            for event, entries in codex_hooks()['hooks'].items():
                for entry in entries:
                    for hook in entry['hooks']:
                        result = subprocess.run(hook['commandWindows'], shell=True,
                                                input=payload, text=True, capture_output=True,
                                                env=env, cwd=directory, timeout=30)
                        self.assertEqual(result.returncode, 0, result.stderr)
                        if event == 'Stop':
                            self.assertEqual(result.stdout, '')
                        else:
                            self.assertIn('main agent', result.stdout)
            # Current Stop guards block through JSON with exit 0. Check that
            # the PowerShell parent preserves this safety decision as well.
            transcript.write_text(json.dumps({'type': 'event_msg', 'payload': {
                'type': 'token_count', 'info': {'last_token_usage': {
                    'input_tokens': 220001, 'output_tokens': 5, 'total_tokens': 220006}}}}) + '\n')
            hook = codex_hooks()['hooks']['Stop'][0]['hooks'][1]
            result = subprocess.run(
                ['powershell.exe', '-NoProfile', '-NonInteractive', '-Command', hook['commandWindows']],
                input=payload, text=True, capture_output=True, env=env, cwd=directory, timeout=30)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(json.loads(result.stdout)['decision'], 'block')
