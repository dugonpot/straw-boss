# Native Windows Codex hooks

Codex lifecycle hooks have a Windows-only `commandWindows` override. See the
[official hook reference](https://learn.chatgpt.com/docs/hooks).

Straw Boss uses that override for SessionStart and both Stop guards. Windows
PowerShell resolves the same plugin roots as the POSIX command, in order:
`CLAUDE_PLUGIN_ROOT`, `STRAW_BOSS_PLUGIN_ROOT`, then the Gemini installation under
the user's home directory. It invokes the existing Python guard through `uv run
--script`, preserving stdin, stdout, stderr, and exit status. It does not depend
on executable permission bits, shebang execution, or a POSIX shell. Missing
roots produce a JSON skip message after consuming stdin.

The Windows entry uses `-EncodedCommand` so an outer PowerShell does not expand
its variables before the inner PowerShell receives them. Its readable source is
`scripts/sync-codex-windows-hooks.py`; run that script after changing the wrapper.
The manifest regression test checks that generated commands match this source.

The context renewal Stop guard also imports usage storage after reading a
Codex rollout transcript. That storage previously imported POSIX-only `fcntl`
unconditionally. The shared exclusive lock now uses `flock` on POSIX and a
blocking byte-range lock on Windows, released when its descriptor closes.
This preserves mutual exclusion rather than bypassing storage protection.
This does not make all opt-in Jev private storage Windows-compatible; that
separate subsystem still uses POSIX descriptor-relative filesystem APIs.

## Verification

On Windows with Codex CLI 0.163.0 and Python 3.13:

```text
uv run --with pytest pytest -q tests/test_file_lock.py tests/test_provider_hook_manifests.py tests/test_skill_instruction_quality.py
43 passed, 1 skipped, 134 subtests passed
```

Coverage includes cross-process lock contention and release, plugin roots with
spaces, root fallback, Unicode input, guard diagnostics and nonzero exits,
missing roots, and all three real guards with an isolated home and a low-token
Codex rollout transcript. The POSIX shell integration test is skipped on Windows.

The required full-suite command was attempted. The existing lifecycle fixtures
set `HOME` but leave `USERPROFILE` intact, so Windows `Path.home()` does not use
their temporary directories. The suite cannot be reported as passing on this
host; a broader run was interrupted after repeated failures. Full-suite Windows
fixture isolation and opt-in Jev filesystem portability need separate work.

The installed 0.33.0 cache is unchanged. Version 0.33.1 in the source manifests
identifies this proposed release; publishing a PR does not deploy it to existing
sessions. Actual dispatched-worker completion and subsequent coordinator
handoff must still be exercised with the repaired version loaded before claiming
end-to-end recovery.

Initial CLI attempts exited successfully without callback markers and did not
establish hook execution. A subsequent native Codex app-server 0.163.0 run used
an isolated home, trusted the exact reviewed hook definitions through
`config/batchWrite`, and started a real read-only model turn. It reproduced
three code-1 hook failures with the original nested `-Command` wrapper.
After switching to `-EncodedCommand`, that same run emitted successful
`hook/completed` events for SessionStart and both Stop guards, with three
independent callback markers identifying the actual guard scripts. The turn
completed successfully. This verifies native runner execution; it does not
yet establish dispatched-worker terminal reporting and coordinator handoff.
