---
name: boss-say
description: Use when the user or prompt explicitly names boss say, or when work spans multiple managed apps.
---

# Boss Say

The main agent splits the work, briefs workers, answers for the user, and reports. Workers are Pi sessions launched with `subagent`; each result arrives as a message.

## Split the work

Find the owning app of each part in the [apps configuration](references/apps-config.md); ask when a part matches no app or several.

- Carry bounded work in this session; dispatch only work that needs its own app checkout or runs in parallel.
- One task is the largest piece one worker can finish end to end in one app.
- Parallel writers to the same app each get their own git worktree, created before launch; a lone writer uses the app checkout.
- A task that needs another task's output waits for it, and its brief names the artifact path.
- Track every task as a todo item that names the tasks it waits on.

## Brief a worker

The `task` brief, in English, carries:

- the requirement: the current symptom and the required behavior;
- the Reality anchor that observes the result;
- the user's authorizations and exclusions, quoted.

Leave the cause, the code location, and the app's conventions to the worker, because a guessed cause binds it to the guess. End the brief with: "When you need a decision these authorizations do not cover, call `caller_ping` and stop."

## Talk with workers and the user

- Collect every pending `caller_ping`, ask the user all of them in one `ask_user` round with a recommendation each, then continue each worker with `subagent_resume` carrying its answer.
- Check each result against its brief before marking the task done; a result that misses the brief becomes a fix task.
- A change to a shared contract, permission data, or a migration gets one fresh-context `reviewer` before merge, because self-review has missed findings there.
- Merging into a shared branch or deploying needs the user's authorization for that target.

## Report

Lead with what landed and its commit or MR. Then list what failed or is blocked, what was left out, and the decisions the user owns, asking those together through `ask_user`.

**Complete when:** every task is done, or blocked with its reason reported, and its worktree is removed.
