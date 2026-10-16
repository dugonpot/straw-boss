# Plan mechanics

[boss-say](../../boss-say/SKILL.md#plan-and-schedule) owns scheduling; this file holds persisted formats and queries.

## Plan file

The main agent writes `~/.straw-boss/plans/<plan-slug>/plan.json` plus sibling `status/` and `artifacts/` directories; it alone mutates the plan.

```json
{
  "plan_id": "p-<slug>",
  "created_at": "2026-09-11T10:00:00+08:00",
  "status": "planning",
  "tasks": [
    {"task_id": "t1", "app": "api", "description": "Required outcome", "depends_on": [], "status": "planned"},
    {"task_id": "c1", "app": "api", "description": "Checkpoint over t1", "depends_on": ["t1"], "status": "planned"}
  ]
}
```

Task status moves `planned` → `dispatched` → `done`/`failed`/`cancelled` (`dispatch-task.py write` and `wrap-up-task.py` record it); `plan.status` goes `planning` → `in-progress` → `done` once every task is terminal.
When a dependent needs a prerequisite's output, name `artifacts/<task-id>-<label>.<ext>` in both briefs; a dependency edge carries ordering, not content.

## Status directory

A plan task's status lives in `status/<task-id>.json` (`{"status", "note", "timestamp"}`); a standalone dispatch's is the instruction's `.status.json`. Terminal values are `done`, `failed`, and coordinator-authored `cancelled`. `awaiting-*` checkpoints stay `dispatched` and hold their slot.

## Read plan state

`read-plan-status.py --plan <slug>` with `--task <id>` (one task), `--not-done` (unfinished, including the queue), `--in-flight` (dispatched, non-terminal; slot accounting), or `--ready` (planned, prerequisites all `done`; scheduler candidates).

## Monitor plan status

Run one `watch-plan-status.py --plan <slug>` through the harness's background facility. It emits the persisted states at startup and each later status revision, and does not stop itself: stop it when every plan task is terminal. Send events to boss-say's scheduler; clean up through [wrap-up](../SKILL.md#wrap-up), then [git lifecycle completion](../../shipping-task/SKILL.md#complete-the-lifecycle).

## Same-task continuation

Before wrap-up, keep the instruction and pane when the user or plan already established a later phase of the same logical task; a different task gets a fresh dispatch. This runs only from a terminal status.
Claude: first `send-dispatch-message.py --instruction-path <path> --to worker --intent control --message "/compact <focus>"`. Then, and alone for Codex, `--intent redirect --message "Continue from the referenced instruction." --ref "<next-phase artifact>"`; the artifact holds the next phase and `report-task-status.py --instruction-path <path>`.

## Worktree ownership

The main agent creates each team-mode worktree with plain git, resolving `<app_dir>` from the app configuration:

```bash
git -C "<app_dir>" worktree add --no-track "<app_dir>-<slug>" -b "<branch>" "<base_branch>"
git -C "<app_dir>-<slug>" rev-parse --show-toplevel
```

The top-level path must be the new worktree. If `extensions.worktreeConfig` makes it resolve to the primary checkout, merge `[core] worktree = <absolute-worktree-path>` and `bare = false` into the worktree's `config.worktree`, verify again, and treat a failed repair as a dispatch blocker.
The verified path becomes `repo_root`, dispatched with `--owns-worktree`.

### Local files

After verification, copy the app's declared `localFiles` ([schema](../../init/references/apps-config-schema.md)):

```bash
copy-local-files.py --repo-root "<repo-root>" --app "<app>" --worktree "<absolute-worktree-path>"
```

A missing entry is an error by default: stop before launching the worker and report its path and note. Skip a missing source only when that exact entry has `optional: true`. Add `--allow-sensitive` only with user authorization covering the sensitive entries.

### Moving base and removal

When parallel tasks target the same moving base or the remote base advanced, have the worker refresh through the app's merge/rebase workflow before pushing, resolve conflicts, and verify the result; otherwise the app's usual pre-push sequence applies.
After [dispatch cleanup](../SKILL.md#wrap-up), the git lifecycle owner runs `git -C "<app_dir>" worktree remove "<absolute-worktree-path>"`.
