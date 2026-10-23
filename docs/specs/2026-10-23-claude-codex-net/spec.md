# Claude Code and Codex sessions in the straw net

Status: approved (design, not implemented). Date: 2026-10-23. The boss chose the recommendation for every open decision (D1 to D8) on 2026-10-23.
Repositories: `straw-boss` (this repository) and `pi-straw-boss` (`~/projects/pi-straw-boss`).

## Intent

The boss's decision, translated: "Claude and Codex sessions are in the net too, as main or member; they can call the tower and broadcast, and the GUI shows them. straw-boss's original dispatch scripts stay unchanged."

Today the straw net is pi-only. A Claude Code or Codex session in a Herdr tab is invisible to the tower dashboard, the sidebar net view, and `/boss gui`. It cannot receive `boss_broadcast`. It can reach a running tower only by hand, with the read-only recipe in `docs/specs/2026-10-17-pi-boss-extension.md:320`.

This spec makes such a session a first-class net unit at the smallest cost. It does this by giving the session the two things the net already keys on: a live pi-intercom session and an `sb_role` pane token.

## Scope

- In:
  - Claude Code and Codex main-agent sessions (sessions the straw-boss SessionStart hook primes with the orchestrator stance) that run in a Herdr pane of a workspace that is not a sub workspace.
  - Presence, liveness, and leaving.
  - Member and main roles, with the same election as pi.
  - `call_tower`, `boss_broadcast`, `boss_status`, `boss_promote`, and `boss_rename` equivalents.
  - Receiving net messages inside the session.
  - Showing the unit in the GUI, the tower dashboard, and the sidebar.
- Out:
  - Dispatched straw-boss workers and coworkers. They stay outside the net, as pi subagents do.
  - Antigravity.
  - Any change to straw-boss dispatch scripts (`dispatch-task.py`, `launch-dispatched-agent.py`, `dispatch-coworker.py`, `send-dispatch-message.py`, the status and wrap-up scripts).
  - GUI comms, typing, terminal mirror, and dialog answers for Claude and Codex units (see D2).
  - Stash and pop of bases that hold such units.
  - A tower that is not pi.

## Reality anchor

The anchor is **pseudo-human**: task 7 runs a real Claude Code and a real Codex session next to a pi in scratch workspaces of the default Herdr. It watches the GUI, the dashboard, and the panes for each acceptance item. The checkpoint is `verification.md` in this directory, written after tasks 4 and 6. Testing (both suites, against `FakeHerdr`, `FakeBroker`, and pytest fakes) gates each task before that.

## What the net keys on (evidence)

| Fact | Evidence |
| --- | --- |
| A net unit is a live intercom session whose Herdr pane carries `sb_role` (`main`, `member`, or `tower`). Status, broadcast, dashboard, and GUI all use that test. | `pi-straw-boss/src/reach.ts:11-17` (`netMembers`), `src/net.ts:29,44-47`, `src/dashboard.ts:198-200` |
| Nothing in that test requires the pane to run pi. Only GUI control, mirror, stash, and subagent linking check `agent === "pi"`. | `src/net.ts:41,68,73`, `src/control.ts:132,195`, `src/mirror.ts:73`, `src/stash.ts:108`, `src/dashboard.ts:173-180` |
| A unit's state comes from its intercom `status`. When the session sets none, it falls back to Herdr's `agent_status` (`blocked` means waiting). Herdr reports that status for Claude and Codex panes. | `src/dashboard.ts:42-47` (`sessionMark`); `herdr agent prompt --help` lists idle/working/blocked/done |
| The tab's main is recorded by the owner of the tab channel `straw-boss/tab/<hex tab id>` (earliest owner-eligible registration), through `commitState`. Claims are channel messages to the owner. | `src/membership.ts:24-31,97-112`, `src/election.ts:6-21` |
| The owner also runs the guard. It promotes under a live tower and clears mains without one, and it may open the tower itself (two members while another base has a tower). | `src/guard.ts:20-44` |
| The tower is always a pi that Herdr starts (`herdr agent start --kind pi`). Any process that can run `herdr` can open one. | `src/towertab.ts:47-63`, `src/herdr.ts:171-172` |
| The modules for membership, election, guard, presence, reach, and digest touch pi only through `pi.events` (`intercom:extension-register`, `intercom:outbox-request`/`result`), `me()` from `env.PI_INTERCOM_SESSION_ID`, and `herdr`. | `src/state.ts:17,84-105`, `src/membership.ts:29`, `src/reach.ts:6-38`, `src/presence.ts`, `src/election.ts`, `src/guard.ts` |
| pi-intercom's raw `IntercomClient` registers a session with `herdrPaneId`, extension capabilities, and an optional `status`, and it can publish extension messages and commit extension state. The broker resolves `herdrLocation` from `herdrPaneId` against a live Herdr snapshot. | `~/.pi/agent/npm/node_modules/pi-intercom/types.ts:142-176`, `broker/client.ts:173,597-600,789`, `herdr-location.ts:40-136`, `broker/broker.ts:548-575` |
| pi-intercom's own extension channel is a thin wrapper over that client (snapshot, publish, commitState, listSessions). | `pi-intercom/index.ts:885-935` |
| The pi-intercom CLI connects, sends, and disconnects. It cannot stay in the roster or receive messages after it exits, so it is no presence. | `pi-intercom/cli.ts:1-20,143-154,193-317` |
| Node refuses to strip types in files under `node_modules` (`ERR_UNSUPPORTED_NODE_MODULES_TYPE_STRIPPING`). pi-intercom starts its own broker with the sibling `tsx` loader. | Ran a scratch `.ts` under `node_modules` with Node 24.21.0; `pi-intercom/broker/spawn.ts:37-53` |
| straw-boss primes every non-dispatched Claude or Codex session with the orchestrator stance at SessionStart, and recognises a dispatched worker by its `session_id` in a dispatch instruction. | `scripts/orchestrator-priming.py:53-63,116-128` |
| The Codex hook manifest may hold only `SessionStart` and `Stop`. A test pins it, and Codex 0.155.1 rejects unknown fields. | `tests/test_provider_hook_manifests.py:27-31` |
| An orchestrator record is `~/.straw-boss/orchestrators/<kind>-<provider session id>.json`. `dispatch-task.py write` creates one when the session dispatches without registering. | `scripts/straw_boss/orchestrator.py:123`, `CONTEXT.md` (Orchestrator directory) |
| straw-boss already types messages into Claude and Codex panes with `herdr agent prompt`, using a `--wait` gate from idle, done, or blocked. | `scripts/straw_boss/herdr/transport.py:163-180` |
| The current net makes mains by promotion, not by first join. Every session joins as a member. | `pi-straw-boss/README.md` (Why), `src/membership.ts:78-95` |

## Design

### Presence: a per-pane net sidecar

A **net sidecar** is one Node process per Claude or Codex main-agent pane. It is the session's net presence:

- It registers with the local pi-intercom broker as a session with:
  - id `<kind>-<provider session id>` (for example `claude-085ff3b1-…`);
  - name `<kind>-<first 8 hex>` until renamed;
  - model `claude-code` or `codex`;
  - `herdrPaneId` from `HERDR_PANE_ID`;
  - no `status`, so the unit's state follows Herdr's `agent_status`;
  - the tab channel `straw-boss/tab/<hex tab id>`, owner-eligible.

  It starts the broker when none runs, as pi-intercom does (`spawnBrokerIfNeeded`).
- It writes `sb_role` and the display tokens (`sb_order`, `sb_mark`, `sb_main_tab`/`sb_tab`) on its pane. It refreshes them every 4 minutes and rewrites them when a new Herdr server takes over, through the existing `presence.ts`.
- It writes the digest line `<name> joined tab <label>`.
- Code: `pi-straw-boss/src/agent/`, which reuses `membership.ts`, `election.ts`, `guard.ts`, `presence.ts`, `reach.ts`, and `digest.ts` unchanged. A small headless kit provides `pi.events` over a raw `IntercomClient`:
  - `intercom:extension-register` becomes a channel object that mirrors `pi-intercom/index.ts:885-935`;
  - `intercom:outbox-request` becomes `client.send` and answers with an `intercom:outbox-result`.

  Briefing is a no-op: Claude and Codex get their stance from straw-boss, not from pi prompts.
- It runs under `node --import <tsx loader>` (the loader pi-intercom resolves for its broker). The path is resolved once at join.

**Who starts it.** straw-boss's existing SessionStart hook, `scripts/orchestrator-priming.py`, starts it, only where it already returns the orchestrator stance (a fresh or renewed main agent). It calls a new `straw_boss/net.py`, which:

1. Skips silently when any of these hold:
   - `HERDR_PANE_ID` is unset;
   - the pi-straw-boss package or `tsx` is not found;
   - the payload is Antigravity;
   - the session is dispatched.

   The net is optional for straw-boss users without pi.
2. Starts `cli.ts join --pane … --kind … --session … --record <orchestrator record path> --cli <absolute path of scripts/straw-net.py>` detached, and returns at once, inside the hook's 10 s timeout.
3. Appends a short **Straw net** section to the priming text. The section names the commands in `scripts/straw-net.py`, and it says that net messages arrive as `[straw net …]` lines.

No hook manifest changes, so the Windows command generator and its tests stay as they are.

**One sidecar per pane.** The sidecar holds `<state dir>/agents/<sha256(pane id)[:16]>.json` (its pid, session, and kind) and the control socket `<same>.sock`, with mode 600 in a 700 directory. The state dir is pi-straw-boss's `straw-boss` directory under `PI_CODING_AGENT_DIR` or `~/.pi/agent`.

A join for a pane whose sidecar is alive behaves as follows:

- Same session: the join does nothing.
- Another session (Claude `/clear`, or a resume into the same pane): the join tells the old sidecar to stop, waits for it to leave, then starts.

**Leaving.** The sidecar leaves within 10 s of any of these:

- Herdr reports its pane closed or exited;
- the pane's `agent` is no longer `claude` or `codex` (it re-reads on `pane.*` events and on a 5 s poll while the events connection is down);
- the stop command.

To leave, it clears its pane tokens (`presence.clear`), then disconnects, so the broker sends `session_left`. A hung sidecar is dropped by the broker's liveness check: it registers `livenessIntervalMs` (`broker/broker.ts:324-326`).

**Sub workspaces.** A pane in a linked-worktree workspace never joins, as for pi (`src/session.ts:32-40`). The sidecar checks this and exits.

### Roles

- **Member at join**, like every pi. The tab channel election and the guard run unchanged in the sidecar. A Claude or Codex sidecar can be a tab's channel owner, deciding pi claims and running the guard. When needed it opens the tower, which is always pi.
- **Main by promotion.** The sidecar promotes, without force, when the orchestrator record file it was given appears or its mtime changes. That happens when `register-orchestrator.py --scope …` runs or when `dispatch-task.py write` auto-registers. This is the straw-boss counterpart of pi promoting on `subagent`, and no dispatch script changes for it (see D1).

  `straw-net.py promote` promotes by hand.

  A tab that already has a live main refuses, as for pi, and the session stays a member. straw-boss still lets it dispatch its own workers: the registry and the net are independent.
- `/boss` (forced takeover) stays a pi command. A pi session can take over a tab from a Claude main.
- A main demoted by the guard (its tower quit) is promoted again only on the next record change, not on every dispatch. See Risks.
- Towers stay pi. `boss_open_main` keeps opening pi mains.

**Orchestrator directory and the net: keep both, map one way.** The straw-boss directory keeps its job: scope text, the delivery ledger, and Herdr-validated deltas between straw-boss mains. The net keeps its job: presence, the tab main, the tower, and broadcasts. The only link is the one above: a record for this session promotes it in the net. Nothing writes the directory from the net. `send-orchestrator-message.py` and the net's `send` are two transports. A straw-boss main can reach a pi main only through the net.

### Messaging

The agent-facing commands live in `scripts/straw-net.py`, a uv script like the other public scripts. It resolves the package and `tsx`, then runs `cli.ts <command>`. That command talks to this pane's sidecar over its socket, found by `HERDR_PANE_ID`.

| Command | pi counterpart | Behavior |
| --- | --- | --- |
| `status` | `boss_status` | Same JSON as `reach.status()`. |
| `promote` | `boss_promote` | `membership.promote(false)`; refused while the tab has a live main. |
| `call-tower --message M [--workspace W]` | `call_tower` | `reach.openTower(W)`, with create when this unit is main, then `send`; same errors. |
| `broadcast --message M [--scope tab\|workspace\|towers\|all]` | `boss_broadcast` | `reach.broadcast`; default `workspace`. |
| `send --to ID --message M` | intercom `send` | One message to one session; this is how the agent replies. |
| `rename --name N` | `boss_rename` | Intercom presence `name` and a digest line. |

**Receiving.** The sidecar takes each intercom `message` addressed to it and types one line into its pane with `herdr agent prompt <pane> <text>`. It uses the same `--wait --until` gate as `transport.py:163-180` when the pane is idle, done, or blocked. The line is:

```text
[straw net from=<name> id=<session id> role=<tower|main|member|session> reply="<straw-net.py> send --to <session id> --message '…'"] <message, newlines folded to spaces>
```

- A pane that is `blocked` (Herdr answers `agent_blocked` before sending any input) is not typed into. The message waits in an in-memory queue, delivered in arrival order when Herdr reports the pane idle, done, or working.
- A message still queued when the sidecar leaves is lost. The sender already got `sent`, as with any intercom message to a session that then quits.
- This reaches the session from the tower (its replies go out with intercom `send`), from `boss_broadcast` of any scope, from pi members telling their main before they dispatch, and from the orphan nudge. The orphan nudge never targets a Claude unit, because it only nudges pi subagents.

### What the GUI and the dashboard show

With no GUI code change:

- The unit is on the map in its tab's squad, as main or member, under its name.
- Its state comes from Herdr. Waiting on a Claude or Codex permission prompt raises the usual waiting alert, answered in the terminal.
- It counts toward its base's mark, appears in the tower dashboard and in the sidebar net view (from the tokens), and shows in join and leave log lines.
- `control` is `false` (`src/net.ts:68`): the composer says nothing can be typed into it, Quit is disabled (`gui/quit.ts:18`), and no comms log or terminal mirror opens, because both require a pi session file (`src/control.ts:132`, `src/mirror.ts:73`).
- Stash and close-all of its base refuse with "pane … runs claude, which Straw Boss cannot ask to quit" (`src/stash.ts:108`). That is the safe default (D5).

One small addition: `Unit.agent` (`"claude"` or `"codex"`, set in `buildNet` from the pane when it is not pi). The page shows it as a badge on the unit and in the composer's notice, so an empty comms panel reads as expected, not broken. Dialog answers, typing, and transcript comms are D2.

### Interaction with `feat/gui-takeover`

A worker is building GUI server takeover when the owner session ends (at the time of writing, the branch does not exist locally; `git branch` and `git worktree list` show only `main` checked out). Sidecars never host the server and never register the dialog channel `straw-boss/gui/<hash>` (`how-it-works.md`, "What it writes").

- If the takeover chooses the next owner through that owner-eligible channel, nothing interacts.
- If it chooses from `listSessions()`, it must skip sessions whose model is `claude-code`, `codex`, or `pi-intercom-cli`.

Order: build this after `feat/gui-takeover` merges. Both touch `src/net.ts` and `tests/imports.test.ts` budgets.

## Acceptance criteria

- [ ] In a scratch Herdr workspace (default Herdr, see pi-straw-boss `AGENTS.md`), a tab with one pi and one Claude main-agent session shows both in `/boss gui`, the tower dashboard, and the sidebar. The Claude unit's mark follows its Herdr state, and a permission prompt shows as waiting.
- [ ] A Codex session in the same tab shows the same way.
- [ ] A dispatched straw-boss worker, a coworker, and a session in a linked-worktree workspace never appear.
- [ ] `register-orchestrator.py --scope …` in the Claude session makes it the tab's main within 5 s when the tab has none. With a live pi main it stays a member, and `status` says who the main is.
- [ ] `straw-net.py call-tower` from a Claude main with no tower opens the pi tower. The tower's intercom reply appears in the Claude composer as one `[straw net …]` line and starts a turn when the pane was idle.
- [ ] `boss_broadcast` with scopes `tab`, `workspace`, and `all` from pi reaches the Claude and Codex panes.
- [ ] `straw-net.py broadcast` from Claude reaches the pi sessions.
- [ ] Quitting Claude removes the unit from the GUI within 10 s and clears its pane tokens.
- [ ] `/clear` rejoins under the new session id with one sidecar for the pane (`ps` shows one).
- [ ] With pi-straw-boss absent, straw-boss's SessionStart output is byte-identical to today's, and no process starts.
- [ ] Both suites pass: `npm run check && npm test` in pi-straw-boss and `uv run --with pytest pytest -q tests` in straw-boss.

## Tasks

Tasks run in order, sequentially in each repository's main checkout. pi-straw-boss work waits for `feat/gui-takeover` to merge.

### 1. Headless kit over a raw intercom client (pi-straw-boss)
- **Files/area:** new `src/agent/kit.ts`.
- **Behavior:**
  - `createHeadlessKit({ client, env, cfg })` returns a `Kit` whose `pi.events` handles the register and outbox events over `IntercomClient`. The channel mirrors `pi-intercom/index.ts:885-935`: owner and state from `extension_owner` and `extension_state`, `publish`, `commitState` with owner epoch and revision, `listSessions`.
  - `me()` is the sidecar id.
  - Every other `pi` member the reused modules do not call throws.
- **Constraints:**
  - Imports `IntercomClient` from the sibling pi-intercom (>= 0.17.1) at runtime.
  - No change to `membership.ts`, `election.ts`, `guard.ts`, `presence.ts`, `reach.ts`.
  - Add a budget line in `tests/imports.test.ts`.
- **Acceptance:** `tests/agent-kit.test.ts` drives the channel with a stub client (owner change, state, claim message, outbox success and failure).
- **Depends on:** `feat/gui-takeover` merged.

### 2. The sidecar (pi-straw-boss)
- **Files/area:** new `src/agent/sidecar.ts`.
- **Behavior:**
  - Registers as in Presence, refuses sub workspaces, and joins via `createMembership(...).joinNet()`.
  - Runs presence, guard, and digest.
  - Watches the record path to promote.
  - Delivers inbound messages with `herdr agent prompt`, using the blocked queue.
  - Watches the pane to leave.
  - Serves the control socket (status, promote, call-tower, broadcast, send, rename, stop).
- **Constraints:** one sidecar per pane through the state file and socket; tokens cleared before disconnect; `PI_*` variables in the inherited environment ignored.
- **Acceptance:** `tests/agent-sidecar.test.ts` with `FakeHerdr` and `FakeBroker` (`tests/fakes.ts:47,224`):
  - a sidecar and a pi `Agent` in one tab both list in `netMembers`;
  - the record file promotes the sidecar, and a live pi main refuses it;
  - a sidecar that owns the channel decides a pi claim;
  - an inbound message produces one `agent prompt` call, and a blocked pane queues it;
  - the pane's agent turning to `null` clears its tokens and leaves.
- **Depends on:** task 1.

### 3. The CLI (pi-straw-boss)
- **Files/area:** new `src/agent/cli.ts`.
- **Behavior:**
  - `join` starts the sidecar detached and returns once its state file exists or after 3 s; a live sidecar with another session is stopped first.
  - The other commands send one request over the socket and print the reply.
  - Exit codes: 0 ok; 1 refused or failed, with the reason on stderr; 2 no sidecar for this pane.
- **Acceptance:** `tests/agent-cli.test.ts` for argument parsing, the no-sidecar error, and join idempotence.
- **Depends on:** task 2.

### 4. Agent badge and docs (pi-straw-boss)
- **Files/area:**
  - `src/net.ts`: `Unit.agent` for non-pi joined units.
  - `gui/render.ts`, `gui/composer.ts`, `gui/messages/{en,zh-TW}.json`: the badge and the composer notice.
  - `gui/fixture.ts`: one Claude unit.
  - `README.md` and `README.zh-TW.md`: Works with.
  - `docs/how-it-works.md`: rewrite "From Claude Code or Codex", and add the sidecar's writes to "What it writes".
- **Constraints:** stay within the `net.ts`+`gui.ts` and page chunk budgets, or raise them with a dated comment as the file does.
- **Acceptance:**
  - `tests/net.test.ts`: a claude pane with `sb_role=member` becomes a unit with `control: false`, `agent: "claude"`, and no file;
  - page build size tests pass;
  - `npm run check && npm test`.
- **Depends on:** task 3.

### 5. Join from the SessionStart hook (straw-boss)
- **Files/area:**
  - new `scripts/straw_boss/net.py` (find the package and `tsx`, build the join argv, return the Straw net priming section or `None`);
  - `scripts/orchestrator-priming.py`: call it on the two orchestrator-stance paths, fresh and renewed `main-agent`, and append the section.
- **Constraints:**
  - Dispatch scripts unchanged; no hook manifest change.
  - Never fail or delay session start: spawn detached, with errors swallowed into a one-line note.
  - Package location: `STRAW_BOSS_PI_PACKAGE`, else `${PI_CODING_AGENT_DIR:-~/.pi/agent}/npm/node_modules/pi-straw-boss`.
- **Acceptance:** `tests/test_straw_net.py`:
  - output is unchanged and nothing spawns without `HERDR_PANE_ID`, without the package, for a dispatched `session_id`, and for an Antigravity payload;
  - a fresh Claude payload and a Codex `rollout-` payload spawn `join` with the right `--kind`, `--session`, and `--record` (`orchestrator.record_path`);
  - `test_session_start_stance_states_each_coordination_rule_once` still passes.
- **Depends on:** task 3 released (or `STRAW_BOSS_PI_PACKAGE` pointing at the checkout).

### 6. Agent command and docs (straw-boss)
- **Files/area:**
  - new `scripts/straw-net.py` (uv script; runs `cli.ts` with the same resolution);
  - the Straw net priming section text;
  - `README.md` and `README.zh-TW.md`: a short "With pi-straw-boss" paragraph;
  - `docs/architecture.md`: one component row and a sentence under "Pi host".
- **Acceptance:**
  - `tests/test_straw_net.py` covers the wrapper's missing-package message and its pass-through exit codes;
  - `test_skill_instruction_quality.py` passes (English surfaces);
  - full suite `uv run --with pytest pytest -q tests`.
- **Depends on:** task 5.

### 7. Live check (both)
- **Behavior:** run the acceptance list in scratch workspaces of the default Herdr with a real Claude Code and a real Codex. Record the result and the PIDs and ports it started, and stop them, in `docs/specs/2026-10-23-claude-codex-net/verification.md`.
- **Depends on:** tasks 4 and 6.

## Risks

- **Typing into a pane the user is typing in.** Inbound lines go through the composer, as straw-boss's own transport does today. A user mid-draft gets the line appended to the draft. This is mitigated only by the blocked-pane queue. D3 offers waiting for idle instead.
- **Pane moves.** The broker locates non-pi sessions by the launch pane id only. Herdr-pi panes are matched by session path (`herdr-location.ts:101-109`). A Claude pane moved to another tab shows as `pane_missing` and drops out of the net until its next SessionStart. That is acceptable for v1, and it is documented.
- **Re-promotion after demotion.** pi re-promotes on every `subagent` call. A Claude main demoted when its tower quit is promoted again only when its orchestrator record changes. `straw-net.py promote` is the manual path.
- **Codex identity.** A Codex record keyed on the Herdr terminal id (old Herdr builds, `orchestrator.py:166-177`) does not match the `--record` path built from the hook's `session_id`, so auto-promotion does not fire. Manual promote still works.
- **Protocol coupling.** The headless channel copies pi-intercom's extension channel (about 60 lines). A pi-intercom protocol change can break it. Pin `>= 0.17.1`, check `supportsFeature("extension-bus-v1")` at join, and fail the join loudly in the sidecar log.
- **Cost.** One more Node process per Claude or Codex main pane (expected tens of MB). Workers never get one.

## Decisions

Resolved 2026-10-23: the boss chose the recommended option in every row.

| # | Decision | Options | Recommendation |
| --- | --- | --- | --- |
| D1 | What makes a Claude or Codex session main | (a) Its straw-boss orchestrator record appears or changes (register or first dispatch). (b) Only `straw-net.py promote`, told by the priming text. (c) A PostToolUse hook on dispatch commands (Claude only; the Codex manifest is pinned to SessionStart and Stop). | **(a)**: deterministic, works for both providers, and touches no dispatch script. Keep `promote` for the manual case. |
| D2 | How much of the GUI covers these units in v1 | (a) Map, state, role, name, alerts, and an agent badge; no comms, typing, mirror, or dialog answers. (b) Also a read-only comms log from the Claude JSONL and Codex rollout transcripts (two new readers in `history.ts` and `items.ts`, and an allow list extended to `~/.claude/projects` and `~/.codex/sessions`). (c) Also the read-only terminal mirror, bound to the pane plus a live sidecar instead of a pi session file. | **(a)** now. "The GUI shows them" is met, and (b) or (c) can follow as a separate spec. |
| D3 | When an inbound net message is typed into the pane | (a) At once, as straw-boss transport does; the provider queues it during a turn; only a blocked pane waits. (b) Hold every message until the pane is idle or done. | **(a)**: a tower reply reaches a working main at its next turn, as with pi steering. Pick (b) if drafts getting extra lines is a real annoyance. |
| D4 | Which Claude and Codex sessions join | (a) Every session primed as a main agent (not dispatched, not a coworker, not in a sub workspace), joining as member at start, as every pi does. (b) Only sessions that registered in the orchestrator directory. | **(a)**: it matches pi's "everyone joins", and (b) would hide members. |
| D5 | Stash and close-all of a base with Claude or Codex units | (a) Refuse, naming the pane, as today. (b) Quit them through `herdr agent send-keys` and close the pane. | **(a)**: quitting a Claude or Codex session by keys is the screen-reading hazard pi-straw-boss `AGENTS.md` warns about. |
| D6 | Where the sidecar code lives | (a) pi-straw-boss `src/agent/`, reusing election, guard, and presence. (b) A Python port in straw-boss. | **(a)**: one implementation of the net's rules. straw-boss only launches it. |
| D7 | Antigravity | (a) Out of scope. (b) Include it (its SessionStart output is `injectSteps`, and Herdr reports it as `agy`). | **(a)**, until the boss asks. |
| D8 | Role-change notices inside the session | (a) None; `straw-net.py status` tells the role, and the GUI shows it. (b) Type a one-line notice on promotion or demotion, which starts a turn on an idle pane. | **(a)**: straw-boss's own stance already governs a Claude main, and an extra turn costs tokens for no action. |

## Commands run (read-only)

- `git status`, `git branch`, `git log --oneline -5`, and `git worktree list` in both repositories.
- `herdr --version` (0.9.5), `herdr pane list | jq …` (pane fields and tokens), `herdr agent prompt --help`, and `herdr agent --help`.
- `node --version` (v24.21.0). A scratch `.ts` under a temporary `node_modules` failed with plain `node` and ran with `node --import ~/.pi/agent/npm/node_modules/tsx/dist/loader.mjs`; the temporary directory was removed.
- Source reads with `sed`, `grep`, and `cat` of the files cited above, and of `~/.pi/agent/npm/node_modules/pi-intercom` 0.17.1.
