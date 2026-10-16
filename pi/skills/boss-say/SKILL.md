---
name: boss-say
description: Use when work involves several agents or sessions: splitting work across workers or managed apps, coordinating or relaying between sessions, or broadcasting to them.
---

# Boss Say

Split the work by owning app from the [apps configuration](references/apps-config.md). One task is what one worker finishes end to end in one app; parallel writers in one app each get a worktree, and a task that needs another's output waits for it.

Brief each worker in English with the required behavior, the Reality anchor, and the user's authorizations quoted; leave the cause and code location to the worker. End with: "When you need a decision these authorizations do not cover, call `caller_ping` and stop." Answer pings through the user, then `subagent_resume` the worker.

Check each result against its brief. Merging to a shared branch or deploying needs the user's authorization for that target.

Broadcast by sending once to every other session; do not filter by name, since a `subagent-chat-*` session can be a main one:
`cli=~/.pi/agent/npm/node_modules/pi-intercom/cli.mjs; node $cli list --json | jq -r --arg me "$PI_SESSION_ID" '.sessions[] | select(.id != $me) | .id' | while read -r id; do node $cli send --to "$id" --text "<message>"; done`

Done when every task has landed or is reported blocked, and its worktree is removed.
