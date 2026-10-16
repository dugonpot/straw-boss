---
name: dispatching-work
description: Use to launch, track, list, or wrap up a resolved app-rooted dispatch.
---

## Prepare the dispatch

Confirm `herdr status` and the `$HERDR_PANE_ID` live record.
Resolve the [worker setup](references/dispatch-mechanics.md#resolve-the-worker-setup), register through [contacting-orchestrators](../contacting-orchestrators/SKILL.md), and [record this session's fingerprint](references/dispatch-mechanics.md#record-the-main-agent).
Team-mode cwd: [shipping-task](../shipping-task/SKILL.md#prepare-and-execute).

## Write the brief

About 300 words:

- **The work** -- per item the current symptom and required behavior, the user's exclusions, and any input, path, or port the worker cannot reach itself. Earlier findings are evidence references.
- **The anchor and who exercises it** -- the anchor, what it observes, and whether the worker runs its own checkpoint or hands its evidence to a shared one. The worker and user choose the verification method inside that anchor.
- **Its place and motive** -- where the task sits and why.

Leave out the cause, code location, and conventions: target-app discovery and work decisions stay with the worker. Name a method skill only on the user's request.
Apply [choosing-graph](../choosing-graph/SKILL.md) if graph and anchor are unset. A shared-checkpoint task passes `--shared-checkpoint`; its [checkpoint task](../choosing-graph/SKILL.md#review-checkpoint) gets a review-only brief of each covered task's requirement and evidence.
Then [write the instruction](references/dispatch-mechanics.md#write-the-instruction).

## Launch

Run [launch-dispatched-agent.py](references/dispatch-mechanics.md#launch) in the foreground until it exits. Require `confirmed: true`, else follow its repair command or [When a launch fails](references/dispatch-mechanics.md#when-a-launch-fails).

## Handle events

Persisted status drives the lifecycle (plans: the [status watcher](references/plan-mechanics.md#monitor-plan-status)).

- `awaiting-main-agent`: answer with `reply-to-worker.py` (verified fact or coordinator result); route a work decision to the user.
- `awaiting-user-input` / `awaiting-authorization`: point the user to the worker pane; only `--intent inform` stays open. Retain the task and its slot.
- `done` / `failed` / `cancelled`: check [same-task continuation](references/plan-mechanics.md#same-task-continuation), wrap up, and return the result to the scheduler.
- Feature-branch push FYI: relay it; status stays as recorded.

[Redirect, cancel, and identity repair](references/dispatch-mechanics.md#redirect-cancel-and-repair) hold the other commands.

## List outstanding dispatches

Run [roll-call.py](references/dispatch-mechanics.md#roll-call) (`--mine` for this session). Resolve an `unattributed` pane's ownership before acting.

## Wrap up

1. Require terminal status; if the pane is closed or a live worker's report is refused, [recover it](references/dispatch-mechanics.md#recover-a-closed-worker). A never-launched instruction needs no status.
2. For a landed programming change, settle [choosing-graph's review checkpoint](../choosing-graph/SKILL.md#review-checkpoint) first.
3. [Close only the terminal worker's pane](references/dispatch-mechanics.md#close-a-worker-pane) (the coordinator pane and shared tab stay open) and [release every remaining lock](references/shared-resource-coordination.md#release-and-inspect).
4. Archive with `wrap-up-task.py --app <app> --slug <slug> [--plan <plan-slug> --task-id <task-id>]`, then run any step its `remaining_steps` names.

**Complete when:** the dispatch awaits its next event, or is terminal, reviewed, closed, unlocked, and archived.
