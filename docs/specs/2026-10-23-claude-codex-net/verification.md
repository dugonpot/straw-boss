# Verification: Claude Code and Codex sessions in the straw net

Task 7 (live check) of [spec.md](spec.md). Date: 2026-10-23, 14:17 to 14:40 (UTC+8).

## Code under test

| Repository | Revision | Checkout used |
| --- | --- | --- |
| `pi-straw-boss` | `feat/claude-codex-net` `7e856e1` | `/tmp/psb-net-ro` (with `node_modules`) |
| `straw-boss` | `feat/claude-codex-net` `460ad2a` | `/tmp/sb-net-ro` |

- The installed `pi-straw-boss` is 0.38.0, which has no sidecar code. The pi session and the two towers in the scratch workspaces ran 0.38.0. The sidecars ran the code under test.
- Claude Code 2.1.309 ran as `STRAW_BOSS_PI_PACKAGE=/tmp/psb-net-ro claude --plugin-dir /tmp/sb-net-ro`. The user's Claude Code has no installed `straw-boss` plugin, so that checkout's SessionStart hook was the only one. No installed plugin or config was changed.
- Herdr 0.9.5 (the default Herdr), pi 1.4.0, Node 24.21.0.
- The scratch workspaces were `netlive-A` (a pi, a Claude Code, the tower the guard opened, and later a dispatched worker and coworker), `netlive-B` (one Claude Code, later its tower), and `netlive-WT` (a linked worktree). The tab and workspace names below are theirs.

## Result

| Requirement | Evidence | Result |
| --- | --- | --- |
| 1. pi + Claude in one tab show in the GUI, the tower dashboard, and the sidebar; mark follows Herdr; a permission prompt shows as waiting | GUI stream snapshot, tower pane read, `herdr agent list` tokens (section 1) | **pass**, with two gaps (agent badge, rendered sidebar) |
| 2. A Codex session in the same tab shows the same way | no `codex` binary (section 2) | **not run** |
| 3. A dispatched worker, a coworker, and a linked-worktree session never appear | no tokens, no sidecar files, GUI snapshot; sidecar log of the worktree pane (section 3) | **pass** |
| 4. `register-orchestrator.py --scope` makes Claude the tab's main within 5 s when the tab has none; with a live pi main it stays a member and `status` says who the main is | token poll and sidecar log: main in about 1 to 2 s; refusal in 1.6 s; `status` JSON (section 4) | **pass** |
| 5. `call-tower` from a Claude main with no tower opens the tower; the reply arrives as one `[straw net ...]` line and starts a turn | pane read of the Claude composer (section 5) | **pass** |
| 6. `boss_broadcast` with scopes `tab`, `workspace`, and `all` from pi reaches the Claude and Codex panes | pi tool results and Claude pane reads (section 6) | **partial**: `tab` and `workspace` pass for Claude; `all` and Codex not run |
| 7. `straw-net.py broadcast` from Claude reaches the pi sessions | command output and pi pane read (section 7) | **pass** |
| 8. Quitting Claude removes the unit from the GUI within 10 s and clears its pane tokens | timed poll of pane, state file, GUI (section 8) | **pass** |
| 9. `/clear` rejoins under the new session id with one sidecar for the pane | state file, sidecar log, `lsof` (section 9) | **pass** |
| 10. With pi-straw-boss absent, SessionStart output is byte-identical to today's and no process starts | SHA-256 of five runs (section 10) | **pass** |
| 11. Both suites pass | pytest and npm output in copies (section 11) | **pass** |

## Evidence

### 1. pi and Claude in one tab

- Setup: `herdr workspace create` for `netlive-A`, `pi` in its pane, then a second pane (split) running the Claude Code command above. Claude Code answered that its SessionStart context had the `## Straw net` section, so the hook ran the code under test.
- Sidecar log of the pane: `joined tab 1 of netlive-A as member`. Pane tokens of the Claude pane: `sb_role=member`, `sb_order=008.1.001.1.001`, `sb_tab`, and `sb_mark` (the same token set as the pi pane).
- Within three minutes of the Claude joining (14:19:20), the tab had two members and other bases had towers, so the guard (pi 0.38.0 or the sidecar) opened a tower tab in `netlive-A` and promoted the pi to main. That is the existing behaviour for two members. Because of it, the main-election checks (4, 5) ran in a second workspace.
- GUI: the machine's GUI server was down (see Observations 1), so the scratch pi started it with `/boss gui`. The stream snapshot (`/<token>/events`, read-only) listed base `netlive-A`, tab 1, with two units: the pi (`role: main`, `control: true`) and `claude-6001531b` (`role: member`, `control: false`, `mark: done`). After `/clear` the second unit became `claude-538e7fef-...`.
- Tower dashboard (read from the tower pane): `this net / tab / <pi> main / claude-6001531b member`.
- Mark follows Herdr: the Claude unit read `idle`, `working`, `done` in step with Herdr's `agent_status`.
- Permission prompt: with Claude Code in manual mode, a prompt for `touch /tmp/netlive/scratch-a/perm-test` made Herdr report `blocked`. The GUI snapshot showed the unit as `mark: waiting`, and the dashboard showed `claude-6001531b member waiting on a ...`.
- Sidebar: the sidebar net view sorts Herdr's Agents list by the `sb_order` token. `herdr agent list` showed the Claude pane with `sb_order` and `sb_role`, ordered under its workspace's tower. **Not observed**: the rendered sidebar itself (it lives in the user's Herdr client).
- **Not verified**: the `Unit.agent` badge from task 4. The GUI that ran was the installed 0.38.0 server (no badge), and `/tmp/psb-net-ro/dist/gui` is not built, so `/boss gui` could not serve the new page. Unit tests cover it.

### 2. Codex

Not run. There is no `codex` binary on `PATH` or in `/opt/homebrew/bin`, `/usr/local/bin`, `~/.local/bin`, `~/.bun/bin`, or the global npm prefix (only the `~/.codex` configuration directory exists). Authentication was not checked, and none was set up.

### 3. Worker, coworker, linked worktree

- Dispatched worker and coworker: the Claude main in `netlive-A` ran the `dispatching-work` skill of the checkout under test and launched one worker (`scratch-a-worker`, pane p4); the worker launched one coworker (pane p5) with `dispatch-coworker.py`. Both panes ran Claude Code with the hook. They had no `sb_*` tokens, no `agents/<hash>.json` or `.log` appeared for them, and the GUI snapshot and the dashboard listed only the pi and the Claude main (`outposts: []`, `outside: []`). Dispatch auto-registered the main's orchestrator record; the sidecar's promote attempt was refused because the tab had a live pi main (log line `Tab ... already has a main agent`).
- Linked worktree: `git worktree add` for `/tmp/netlive/scratch-wt`, then `herdr worktree open` made workspace `netlive-WT` with `is_linked_worktree: true`. Claude Code started there with the same command. The hook started a join, and the sidecar logged `join failed: netlive-WT is a sub workspace, so this session cannot join the net; the main agent of its parent workspace represents it` and `left: the join failed`. The pane had no tokens, no state file remained, and the GUI listed the workspace only as an outpost of `netlive-A` (the same as a pi sub workspace), not as a unit.

### 4. Register promotes; a live main refuses

- Tab with no main: workspace `netlive-B`, one Claude Code (a lone member, so the guard did not act). The session ran `register-orchestrator.py --scope 'net live check B'`. The record file was written at 14:33:17 (second resolution). The pane's token poll (every 0.4 s) saw `sb_role` change from `member` to `main` at 14:33:18.77, and the sidecar log reads `This session is now the main agent of 1` at 14:33:18.38 (UTC 06:33:18.379Z). That is about 1 to 2 s.
- Tab with a live pi main: in `netlive-A` the same command wrote the record at 14:22:13.18, and the sidecar logged at 14:22:14.78: `Tab 2 already has a main agent, <pi name>. Stay a member: ...`. The Claude stayed `member`. The same refusal came again when `dispatch-task.py write` auto-registered, and from `straw-net.py promote` (exit 1).
- `straw-net.py status` (exit 0) printed `me: {id: claude-6001531b-..., role: member}` and `tabs[0].main: 01a16769-2eaf-759b-bb41-9fc2656ba6c4` (the pi's session id), the tab's tower, and the other towers. It names the main by id only; the refusal message names it by name.

### 5. `call-tower`

In `netlive-B` (the Claude was main, the workspace had no tower), the session ran `straw-net.py call-tower --message 'NETCHECK-B: reply to this session with the single word pong using intercom send, nothing else'`. Output: `Sent to the tower of netlive-B. It replies through intercom.` Within the 8 s poll after that a second tab (the tower) existed. The reply appeared in the Claude composer as one line, `[straw net from="tower - netlive-B" id=01a16776-cc74-7520-b5bd-0d3dea533562 role=tower reply="/private/tmp/sb-net-ro/scripts/straw-net.py send --to 01a16776-... --message '...'"] pong`, and Claude Code started a turn on the idle pane and answered it.

### 6. `boss_broadcast` from pi

The scratch pi called the tool in `netlive-A`:

- `scope=tab`: `Broadcast to 1 session(s): claude-6001531b: sent`. The Claude pane was `blocked` on a permission prompt at the time, and nothing was typed into it. After the prompt was approved, the message arrived as one `[straw net from=... id=<pi id> role=main reply="..."] NETCHECK-tab: reply not needed` line and started a turn. This exercises the blocked-pane queue (D3).
- `scope=workspace`: `Broadcast to 2 session(s): claude-6001531b: sent` and `tower - netlive-A: sent`. The Claude pane got the line and started a turn.
- `scope=all`: **not run**. It would type into every live net member of the user's other workspaces, which the task rules forbid. It uses the same `netMembers` path as `tab`.
- Codex: not run (see 2).

### 7. `straw-net.py broadcast` from Claude

`straw-net.py broadcast --message 'NETCHECK-from-claude: no reply needed' --scope tab`, run in a shell with `HERDR_PANE_ID` set to the Claude pane (so it talked to that pane's sidecar; Claude Code itself did not type it), printed `Broadcast to 1 session(s): <pi name>: sent`. The pi pane showed the intercom message `From: claude-6001531b (/private/tmp/netlive/scratch-a)` and started a turn.

Also run the same way, all as expected: `rename --name netlive-claude` (exit 0; the dashboard showed the new name), `send --to <pi id>` (exit 0, delivered), `promote` while the tab had a main (exit 1, reason on stderr), and `status` for a pane with no sidecar (exit 2, `no net sidecar for pane ...`).

### 8. Quit

Polling the pane, the state file, and the GUI snapshot every ~1.5 s while `/exit` ran:

| Session | `/exit` sent | Herdr: pane agent gone | state file gone | tokens cleared | unit gone from GUI |
| --- | --- | --- | --- | --- | --- |
| Claude B (main) | 14:36:53.97 | 14:36:58.0 | by 14:36:59.6 | by 14:37:01.1 | by 14:37:02.6 |
| Claude A (member) | 14:38:20.59 | 14:38:23.96 | by 14:38:27.0 | by 14:38:28.5 | by 14:38:28.5 |

The unit was gone within 4.6 s of Herdr no longer seeing the agent (8.6 s and 8.0 s after `/exit`, because Claude Code takes about 4 s to exit). Sidecar log: `left: the pane no longer runs claude`.

### 9. `/clear`

The pane's state file named session `6001531b-...` (sidecar pid 93808). `/clear` was sent at 14:28:37. The log shows `left: the stop command` at 14:28:39.0 and `joined tab ... as member` at 14:28:39.9. The state file then named session `538e7fef-...` (pid 87643); the old pid was gone, and `lsof` showed one process on the pane's socket. The GUI showed one Claude unit, `claude-538e7fef-...`.

### 10. Pi-straw-boss absent

`orchestrator-priming.py` was fed `{"session_id": "<uuid>", "source": "startup", "hook_event_name": "SessionStart"}` with `HERDR_PANE_ID` set, under these conditions. The output was 1373 bytes, with the same SHA-256 (`eb3b131e149c5be42027cbdb18f915cd922602b892b8561b4ef6e78ea5555328`) as the output of the `main` checkout's hook (today's): the code under test with the installed 0.38.0 (no `src/agent/cli.ts`), with `PI_CODING_AGENT_DIR` pointing at an empty directory, with `STRAW_BOSS_PI_PACKAGE` naming a missing directory, and with `HERDR_PANE_ID` unset. No `agents/<hash>` file for the fake pane appeared, so no join started. (With the package present, the same hook did start the join, see 1.)

### 11. Suites

Run in copies of the two checkouts (`/tmp/netlive/suites/psb` and `/tmp/netlive/suites/sb`) under `env -i` with only `HOME` and `PATH`, so the pretest GUI build and the caches did not touch the read-only checkouts:

- `uv run --with pytest pytest -q tests` in the straw-boss copy: 642 passed, 4 skipped, 263 subtests passed, in 171 s.
- `npm run check` in the pi-straw-boss copy: exit 0.
- `npm test` in the pi-straw-boss copy: 833 tests, 832 pass, 1 skipped, 0 fail.

## Observations

1. **The GUI server was down.** `~/.pi/agent/straw-boss/gui.json` was a stale record (pid 22880 dead, nothing on port 52662). The GUI check needed a server, so the scratch pi started one with `/boss gui` (pid 87461, port 52662, same port and token as the record, no remote listener) and `/boss gui stop` stopped it before the workspace closed. Stop deleted `remote.json` and marked `gui.json` `stopped`. Both were restored byte for byte from a backup taken first (`gui.json`, `paired.json`, `remote.json`, `config.json` compared equal afterwards), so the state is what it was before.
2. **Odd pi name.** After the pi ran `boss_broadcast`, its intercom/net name became `Tool call title: boss_broadcast NETCHECK` and its tab label `Tool call title:...`. Every `[straw net from=...]` line from that pi then carried it. This comes from the pi side (0.38.0 and its extensions), not the sidecar, and was not investigated. Repro: a pi in Herdr, ask it to call `boss_broadcast` once, then run `straw-net.py status` from a Claude in the same tab.
3. **Claude Code writes into a `--plugin-dir` checkout.** Claude Code 2.1.309 created `tsconfig.json` and `.claude-plugin/types/` in `/tmp/sb-net-ro` when it loaded the plugin (at 14:19). Both were removed afterwards; nothing else in that checkout or in `/tmp/psb-net-ro` changed (`git status` is clean; the hooks left ignored `__pycache__` directories).
4. **`status` names the main by id only** (see 4). Fine as specified; a name would read better.
5. **Message format.** The typed line quotes the sender (`from="..."`) where the spec writes `from=<name>`. Harmless; the Straw net priming section shows `from=...` unquoted.
6. **Ordering in 8 could not be resolved.** The state file vanished before the tokens in both runs, but the poll interval (~1.5 s) is larger than the gap, so this does not show whether the sidecar clears tokens first.
7. A mid-run Herdr change outside this check: panes `wRE:p22` and `wRE:p23` of the user's `MP Center` workspace closed during the run. They were not created or touched by this check.

No code bug was found in the code under test.

## Processes, ports, and files

Started (all confirmed gone: each PID checked with `ps -p`, the ports with `lsof`, the scratch workspaces closed, and `herdr pane list` shows no pane that the baseline did not have):

| What | PID / pane |
| --- | --- |
| scratch pi, and the GUI server it ran (port 52662, no remote port) | 87461, pane `wSE:p1` |
| tower pi of `netlive-A` | 94441, pane `wSE:p3` |
| tower pi of `netlive-B` | 26907, pane `wSH:p2` |
| Claude Code A (pane `wSE:p2`) | 92074 |
| Claude Code worker (pane `wSE:p4`), and its MCP helper | 8563, 9178 |
| sidecars of pane `wSE:p2` | 93808, then 87643 after `/clear` |
| sidecar of `wSH:p1`, Claude Code B, the coworker, and the `netlive-WT` Claude Code and sidecar | PID not recorded; gone with their panes (log lines show each left) |

Workspaces `wSE` (`netlive-A`), `wSG` (`netlive-WT`), and `wSH` (`netlive-B`) were created and closed by this check; `wSF` was a first attempt at `netlive-WT` (no worktree), closed at once.

Removed: the three sidecar logs under `~/.pi/agent/straw-boss/agents/` (the directory did not exist before and was removed), 14 files this check left under `~/.straw-boss/` (the `scratch-a--netlive-w` and `scratch-a--netlive-cw` dispatch files and the three orchestrator records of the scratch sessions). The scratch repository, worktree, and logs under `/tmp/netlive` stay until `/tmp` is cleared.

Left behind, outside the state directories (not reverted): Claude Code's own trust-folder entries for `/private/tmp/netlive/scratch-a`, `scratch-b`, and `scratch-wt` in `~/.claude.json`, Claude Code transcripts under `~/.claude/projects/-private-tmp-netlive-*`, and pi session files under `~/.pi/agent/sessions/--private-tmp-netlive-*`.
