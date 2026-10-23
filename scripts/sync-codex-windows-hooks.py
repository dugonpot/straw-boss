#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.11"
# dependencies = []
# ///
"""Regenerate Windows hook commands without nested-shell interpolation."""
from __future__ import annotations

import base64
import json
from pathlib import Path

SCRIPTS = ('orchestrator-priming.py', 'dispatched-agent-stop-guard.py',
           'context-renewal-guard.py')


def windows_command(script_name: str) -> str:
    if script_name not in SCRIPTS:
        raise ValueError('unsupported hook script')
    message = json.dumps({'systemMessage':
        f'straw-boss: plugin root is unset or does not contain scripts/{script_name}; '
        'hook skipped. Restart this session to reload plugin roots.'})
    source = f"""$ErrorActionPreference = 'Stop'
$env:PYTHONUTF8 = '1'
foreach ($root in @($env:CLAUDE_PLUGIN_ROOT, $env:STRAW_BOSS_PLUGIN_ROOT, (Join-Path $HOME '.gemini/config/plugins/straw-boss'))) {{
    if ($root) {{
        $script = Join-Path $root 'scripts/{script_name}'
        if (Test-Path -LiteralPath $script -PathType Leaf) {{
            & uv run --script $script
            exit $LASTEXITCODE
        }}
    }}
}}
$null = [Console]::In.ReadToEnd()
[Console]::Out.WriteLine('{message}')
"""
    # Codex may launch through either cmd.exe or PowerShell. Encoding keeps
    # the outer shell from expanding the inner script's $env and $variables.
    encoded = base64.b64encode(source.encode('utf-16-le')).decode('ascii')
    return 'powershell.exe -NoLogo -NoProfile -NonInteractive -EncodedCommand ' + encoded


def main() -> None:
    manifest = Path(__file__).resolve().parents[1] / 'hooks/codex-hooks.json'
    payload = json.loads(manifest.read_text(encoding='utf-8'))
    hooks = [hook for entries in payload['hooks'].values()
             for entry in entries for hook in entry['hooks']]
    for hook, name in zip(hooks, SCRIPTS, strict=True):
        hook['commandWindows'] = windows_command(name)
    manifest.write_text(json.dumps(payload, indent=2) + '\n', encoding='utf-8')


if __name__ == '__main__':
    main()
