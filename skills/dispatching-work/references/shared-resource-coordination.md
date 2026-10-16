# Shared-resource coordination

`claim-resource.py` locks resources shared by concurrent tasks under one user account on one machine (`~/.straw-boss/locks/`); cross-user or cross-machine access needs resource-side coordination. Resource names use `A-Za-z0-9._-` with `--` as separator.

## Ports

For a configurable port, claim immediately before starting the server and bind the returned `port`:

```bash
uv run --script "${CLAUDE_PLUGIN_ROOT}/scripts/claim-resource.py" claim-port \
  --app "<app>" --key "<absolute-worktree-path>" --holder "<app>--<slug>" \
  --requester-instruction-path "<instruction-path>" --note "dev server for <slug>"
```

Claim once, run the server, then release: a repeated claim reads the caller's own lock as contention and walks to another port.
For a frontend human or pseudo-human checkpoint, the main agent claims before dispatch (`--key` the instruction stem or checkout path, a TTL covering the task) and puts the returned number and the result's `release_command` in the brief verbatim; the worker binds that number and releases with that exact command, since stopping the process leaves the lock held.
A fixed port uses `wait` on `port--<app>--<number>`.

## Shared database and fixed-port locks

Derive a stable identity from the actual target (host and database):

```bash
uv run --script "${CLAUDE_PLUGIN_ROOT}/scripts/claim-resource.py" wait \
  --resource "db-migration--<db-identity>" --holder "<app>--<slug>" \
  --requester-instruction-path "<instruction-path>" \
  --ttl-seconds <expected-hold-duration> --note "<reason>"
```

Set the TTL from the protected operation's duration; a claim is reclaimable after it. If `reclaimed_stale: true`, check the prior holder's dispatch first: expiry alone does not establish that its process stopped. A contended result names the holder; [asking-peer-agents](../../asking-peer-agents/SKILL.md) can get an ETA, but access still needs a successful claim.

## Release and inspect

`claim-resource.py release --resource <id> --holder "<app>--<slug>"` after use; `list --prefix port--|db-migration--` and `status --resource <id>` show holders across this user's main agents; `gc` removes expired locks; `--force` release needs evidence of expiry or the user's confirmation that the holder stopped.
Wrap-up releases every remaining lock on the instruction, for `done`, `failed`, and `cancelled`, before archiving: both the main agent's dispatch-time port claim and any worker-held lock whose release is unconfirmed.
