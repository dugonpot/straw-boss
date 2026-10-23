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
41 passed, 1 skipped, 133 subtests passed
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

An ephemeral, read-only Codex CLI turn was also attempted with the reviewed
hook definitions, explicit hook enablement, and callback tracing. The turn
exited successfully without `Hook failed`, but no callback markers appeared.
That attempt does not establish runner-level hook execution and is not a
passing end-to-end UAT result. Direct real-guard integration tests above remain
the executable evidence for this change.
