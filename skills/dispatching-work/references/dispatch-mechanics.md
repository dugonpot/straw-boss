# Dispatch mechanics

Run each command as `uv run --script "${CLAUDE_PLUGIN_ROOT}/scripts/<name>.py"`; `--help` and the docstring carry argument detail and refusal rules.

## Resolve the worker setup

Pick provider, profile, model, effort, and Claude's optional native advisor in this order: explicit per-dispatch override, the matching root `AGENTS.md` work route (`CLAUDE.md` when it has no route section), the app's `apps.json.agentKind`, Claude with provider defaults. Conflicting routes go to the user ([init](../../init/SKILL.md#configure-work-routes) synchronizes them). Codex and Antigravity record no advisor; report an incompatible combination. State the setup and reason.

The launcher mirrors the main agent's restriction tier, so the worker must never be more permissive. `--main-agent-permission-tier`: omit to inherit, name a tier to override, `none` for no permission flag. A launcher `--agent-arg` permission flag replaces the mirrored one.

## Record the main agent

Every dispatch records `--main-agent-kind`, `--main-agent-pane-id "$HERDR_PANE_ID"`, and the live session fingerprint from `herdr agent get`: Claude `--main-agent-session-id` (`$CLAUDE_CODE_SESSION_ID` when Herdr exposes none); Codex `--main-agent-terminal-id`, plus `--main-agent-session-id` when present.
A different or missing session is a mismatch even in the right pane.

## Write the instruction

```bash
dispatch-task.py write --app <app> --slug <slug> --task "<brief>" \
  --mode herdr-pane --repo-root <verified-cwd> \
  [--batch <batch>] [--plan <plan> --task-id <task>] [--role <workroom>] \
  [--shared-checkpoint] [--owns-worktree] \
  --agent-kind claude|codex|agy --main-agent-kind claude|codex|agy \
  [--agent-profile <p>] [--agent-model <m>] [--agent-effort <e>] [--advisor-model <m>] \
  --main-agent-pane-id <pane> [--main-agent-session-id <s>] [--main-agent-terminal-id <t>]
```

It writes a pending `<app>--<slug>.json` and an immutable `.contract.md`; the brief carries no communication prose.
`--role` labels a workroom. `--shared-checkpoint` makes the worker report its completion reference and evidence while the group's checkpoint task reports the disposition. A plan task also passes `plan_id`/`task_id`, and the command marks it dispatched.
`--owns-worktree` declares `--repo-root` a linked worktree this main agent created ([Worktree ownership](plan-mechanics.md#worktree-ownership)); only then do wrap-up and roll-call name `git worktree remove`. A coworker never passes it.

## Launch

```bash
launch-dispatched-agent.py --instruction-path <path> [--name <agent-name>] [--agent-arg=<provider-arg>]...
```

Run in the foreground to completion. It splits a pane in the recorded main pane's tab, injects the contract, verifies delivery, writes `.launch.json`, and confirms the instruction `in-progress`; omit `--name` for automatic collision handling.
For `confirmed: false`, keep the worker and run the repair the warning names: `dispatch-task.py confirm --app <app> --slug <slug>`.

## When a launch fails

Read the classification, pane excerpt, and `.launch-failure.json`; the launcher retries transient pane errors itself. Fix a configuration, identity, tab, or startup-gate cause before retrying, and continue recovery in a retained pane using its observed choices and the user's authorization.

## Roll call

`roll-call.py [--mine] [--json]` is a pure read reconciling instructions, launch receipts, and live provider identity. Verdicts: `running`/`checkpoint`, `awaiting-collection` (terminal status recorded), `orphaned` (no live match), `never-launched`, `launched-unconfirmed`, `awaiting-startup-gate`. `wrapped_up_open_panes` lists archived dispatches whose pane is still open, with the `remaining_steps` to close it.

## Redirect, cancel, and repair

- Inform: `send-dispatch-message.py --instruction-path <path> --to worker --intent inform --message "<delta>" [--ref <source>]`. A body is one delta in at most two sentences; longer context goes behind repeatable `--ref`.
- Redirect (an explicit user change or an objectively wrong instruction): interrupt the worker pane, confirm it idle, then send `--intent redirect`.
- Cancel only on the user's request or an invalid, duplicate, or unreachable dispatch: interrupt and close the pane, then `report-task-status.py --instruction-path <path> --status cancelled`, and re-check dependents (`cancelled` satisfies none).
- Main agent replaced or moved: `adopt-dispatch.py --instruction-path <path> --main-session-id <this session>` from the new pane.
- Worker restarted in its pane: `adopt-worker-endpoint.py --instruction-path <path> --worker-session-id <live id>`.
- User asks to take over another main agent's dispatches: `take-over-dispatch.py --user-requested --instruction-path <path> [...]`; when it reports `previous_coordinator_live`, `inform` that coordinator through [contacting-orchestrators](../../contacting-orchestrators/SKILL.md).
- Older Codex dispatch after a Herdr restart: `rebind-dispatch.py` with the original main and worker session ids and their rollout `--ref`s.

## Recover a closed worker

`recover-task-status.py --instruction-path <path> --status done|failed --note "<evidence-backed outcome>"` records `recovered_by_main_agent` and `herdr_pane_closed_at`. It refuses a reachable worker or an existing terminal status; pane closure alone establishes only reachability, so decide the outcome from work evidence. When a live worker's own terminal report is refused, add `--worker-cannot-report`; the pane stays open and the command refuses a worker herdr shows `working`.

## Close a worker pane

`close-worker-pane.py --instruction-path <path>` requires the dispatch's own terminal status, closes the pane, records `herdr_pane_closed_at`, and rebalances the surviving columns. It also ends a task parked at `awaiting-user-input` or `awaiting-authorization`.

