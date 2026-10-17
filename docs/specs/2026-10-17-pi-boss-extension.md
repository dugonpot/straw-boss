# Pi Straw Boss extension: the net, main agents, towers, and broadcast

Status: implemented as `pi-straw-boss` 0.1.0 in `~/projects/pi-straw-boss` (not yet
published). Revised 2026-10-17 for the join design, the head tower, the broadcast
rules, and what the live check in Herdr found. Scope: the Pi side only (`pi/`).
The Claude Code and Codex side (`skills/`, `scripts/`) is untouched.

## Intent

Straw Boss on Pi becomes a thin coordination layer: one extension that replaces
the `boss-say` skill. Sessions join a small net by choice, the extension publishes
roles in Herdr, gives every member one way to find and reach the coordinators, and
injects only that role's short prompt. The extension is glue. It does not track
dispatches, allocate resources, or re-implement anything pi-intercom,
pi-herdr-agents, pi-auto-tab-name, or Herdr's pi integration already does.

User decisions this design follows (translated from the user's answers):

| # | Decision |
|---|---|
| U1 | Every Herdr tab with a net has one work coordinator, the **main agent**. The user stays the **boss**. |
| U2 | Every Herdr workspace has one agent-facing coordinator, the **tower** ("pilots talk to the tower, passengers don't"). |
| U3 | A session takes over as its tab's main agent with `/boss`. (Automatic election is superseded by U11.) |
| U4 | The tower is not elected from existing sessions. It lives in its own extra tab, opened when the workspace has none and something needs it. |
| U5 | The tower coordinates agents. The user does not normally talk to it (they may). It does not prompt the user or take focus; decisions for the user go back through the main agent that owns the work. |
| U6 | On Pi the tower also takes the boss assistant role: main agents report Straw Boss coordination friction to it, and it repairs the coordination relationship. There is no separate boss assistant session. |
| U7 | Towers of different workspaces can talk to each other, and any member has a simple way to call a tower: its own or a named workspace's. |
| U8 | v1 scope: identity, naming, `boss_broadcast`, and calling the tower. Sleep and wake flows come later. |
| U9 | Straw Boss stays drastically lightweight (commit e019d96 removed 436-line `dispatch-recovery.ts`, `pane-balance`, and `pi-dispatch.py` for being too heavy). |
| U10 | The main agent, tower, member, and join-reminder prompts are injected by code, so Pi needs no skill: `boss-say` retires on Pi and its rules move into the main-agent prompt. Prompts are small markdown files with word budgets. |
| U11 | Net membership is by choice (2026-10-17). Nothing forces a session in. A reminder asks a main-eligible session once, when its first task starts, whether the current work competes for resources with, or collaborates with, other work in this workspace; a yes joins. A session can also join later with `boss_join` when it finds the need mid-work. The first joiner of a tab is its main agent and stays so; a later joiner is a member and can take over with `/boss`. A session that has not joined is outside the net: no role prompt beyond the one reminder, not listed as a coordinator, no broadcasts except scope `all`. |
| U12 | pi-herdr-agents subagents (`PI_SUBAGENT_ID`) never get the reminder and never join; their parent represents them. They receive only broadcast scope `all`. |
| U13 | `boss_broadcast` scopes `tab`, `workspace`, and `towers` reach only sessions that joined the net, and towers. Scope `all` reaches every pi session on the machine, joined or not, for notices such as the boss going to sleep or waking. The sender is always skipped. |
| U14 | Towers that need to coordinate among themselves (rare) use the **head tower**: the tower of the first workspace in `herdr workspace list` order. No election, no extra channel state. If that workspace has no tower running, `call_tower` to it opens one as usual. |

## Scope

- In: net membership (the join reminder, `boss_join`, `/boss`), the main agent of
  a tab and `/boss` takeover, the on-demand tower tab and the head tower, Herdr
  metadata, the tools `boss_join`, `boss_status`, `call_tower`, and
  `boss_broadcast`, the injected role prompts, and retiring the Pi `boss-say`
  skill.
- Out: sleep and wake flows, dispatch tracking, pane layout, model routing,
  renaming sessions, tab labels other than the tower tab, Claude Code or Codex
  changes, cross-machine sessions, a tower dashboard (v2).

## Vocabulary

| Term | Meaning | Where it lives |
|---|---|---|
| boss | The user. | Identifiers only (`/boss`, `boss_*`), per `CONTEXT.md` "In identifiers, boss means the user". |
| net | The sessions that joined, plus the towers. | Pane token `sb_role` and the tab channels. |
| main agent | The coordinator of one Herdr tab: the first session to join it, or the `/boss` taker-over. | Channel state `main`; pane token `sb_role=main`. |
| member | A joined session in a tab whose main agent is another session. | Pane token `sb_role=member`. |
| tower | The agent-facing coordinator of one Herdr workspace. Also the boss assistant on Pi. | A pi session in a tab labelled `tower`, published as a workspace token. |
| head tower | The tower of the first workspace in `herdr workspace list` order. | Derived, never stored. |
| worker | A pi-herdr-agents subagent (`PI_SUBAGENT_ID` set). | Never joins; the extension returns before registering anything. |

## Reality anchor: the APIs this relies on

Rows marked **live** were observed in a real pi and Herdr during the live check;
the others were read in source (pi-intercom 0.17.1, herdr 0.9.4, pi-auto-tab-name
0.2.0, pi 1.3.0).

| Fact | Evidence |
|---|---|
| Register an extension channel with `{namespace, ownerEligible, onReady, onEvent}`. The registration listener lives at factory level, and a channel registered after the broker connection is synchronized without reconnecting, so joining mid-session works. | pi-intercom `README.md:494-529`, `extension-api.ts:3,80-98`, `index.ts:937-957,2028-2041` |
| Namespace must match `^[a-z0-9][a-z0-9._/-]{0,63}$`; at most 32 channels per session; a namespace registers once and cannot be unregistered. | `broker/broker.ts:39,1511-1522`; `index.ts:941-956` |
| The broker elects one owner per namespace by **connection order** (`ownerOrder`, assigned when the session connects, not when it registers the channel). A session that connected earlier but joins later therefore takes ownership. Clients cannot seize ownership. When no eligible session remains, the owner is cleared. | `broker/broker.ts:75,570,1537-1612` |
| State is ≤ 64 KiB, written only by the current owner and epoch; it persists in the broker's state store. | `broker/broker.ts:41,1805-1830`; `index.ts:909-922` |
| `publish()` ≤ 16 KiB to audience `owner` or `capable`. Events: `connection`, `owner`, `message`, `state`, `state_result`, `session_joined`, `session_left`, `presence_update`. | `broker/broker.ts:40,1630-1705`; `index.ts:1437-1490` |
| `channel.snapshot().connected` is false until the client has connected, which happens after `session_start` (a `setTimeout(0)` in pi-intercom's own `session_start`). **Live:** a handler that waits for it inside `session_start` blocks intercom's own start. | `index.ts:1948-1960`; live check |
| `listSessions()` returns each live session with `herdrLocation` (workspace id/label, tab id/label, current pane id), freshly resolved per request. | `extension-api.ts:90`; `types.ts:15-31` |
| pi-intercom publishes the session's intercom id in `PI_INTERCOM_SESSION_ID`. **Live:** it equals the pi session id. | `index.ts:53,1039,1936`; live check |
| The extension outbox sends an ordinary one-way message as the current session. **Live:** the receiver's `intercom reply` is rejected ("Reply target does not match a pending ask"); a plain `intercom send` to the sender works. | `README.md:531-558`; live check |
| An intercom message wakes an idle session immediately; a busy one gets it at the next safe boundary. Extension-channel traffic never starts a turn. | `README.md:146,496` |
| `before_agent_start` exposes mutable `systemPromptOptions.sections`; changing a section lets pi append a transcript delta, and a deleted key removes the section. | pi `dist/core/extensions/types.d.ts:720-742`; `docs/message-types.md:100-107` |
| pi awaits `session_start` handlers one after another, in extension load order. | **Live** (the tower deadlock below) |
| pi-herdr-agents marks workers with `PI_SUBAGENT_ID`. | pi-herdr-agents `maestro/adapters/pi/launch.ts:918,1079` |
| pi-auto-tab-name skips subagents and non-Herdr sessions, names a tab only from its top-left pane, and only when the label is a bare number or one it set. | pi-auto-tab-name `src/index.ts:136-170` |
| `herdr tab create --workspace --label --cwd --env K=V --no-focus` returns `tab` and `root_pane`; the env reaches the pane's shell. | Ran it; **live** |
| `herdr agent start <name> --kind pi --pane <id> [--timeout ms] -- <pi args>` starts pi at a shell prompt and waits for readiness. **Live:** the name must match `^[a-z][a-z0-9_-]{0,31}$` and be unique across the whole Herdr server (`invalid_agent_name`, `agent_name_taken`). **Live:** started immediately after `tab create`, it answered `agent_pane_busy` ("not an available shell") in 1 of 4 trials, because the new shell was not at its prompt yet. | `herdr agent start --help`; live check |
| `herdr workspace|pane report-metadata <id> --source X [--token K=V] [--clear-token K] [--ttl-ms N]`; tokens read back in `workspace list/get` and `pane list/get`. The positional id comes before the options. TTL max 24 h. | Ran both; **live** |
| `herdr tab close <id>` on the tower's own tab ends its pi cleanly. | **Live** (below) |
| pi project trust: `/private/tmp` and `/Users/weihung/projects` were already trusted in `~/.pi/agent/trust.json`, so a project-local `.pi/extensions` file there loads without changing any configuration. | `docs/security.md`; `trust.json` |

## Coordinator model

| | Main agent (tab tier) | Tower (workspace tier) |
|---|---|---|
| Count | One per tab that has a joined session. | At most one per workspace. |
| Eligible | `HERDR_PANE_ID` set, `PI_SUBAGENT_ID` unset, role is not tower, and the session **joined**. | Only the session started in the tower tab (role `tower`). |
| Chosen by | Join order, pinned in the tab channel's state, overridden by `/boss`. | Created on demand; never elected among existing sessions. |
| Intercom | Channel `straw-boss/tab/<hex(tabId)>`, e.g. `wBB:t1` → `straw-boss/tab/7742423a7431`. Hex keeps Herdr's uppercase and `:` inside the namespace regex; tab ids over 24 characters fail fast. Registered with `ownerEligible: true` **only at join**. | Registers its own tab's channel with `ownerEligible: false` (it needs the channel only for `listSessions`). Session name `tower · <workspace label>`. |
| Herdr | Pane token `sb_role=main` (members: `member`). | Tab label `tower`; Herdr agent `tower-<lowercased workspace id>`; pane token `sb_role=tower`; workspace token `tower=<intercom session id>`. |
| Wakes on | The user, its workers, intercom messages. | Intercom messages only: `call_tower`, `boss_broadcast`, replies. |

A session that has not joined registers no channel and writes no token. A worker
registers nothing at all. The only hosted sessions with channels are joined
sessions and towers.

### Net membership: the reminder and `boss_join`

```text
session_start (main-eligible, not a tower):
  register the tool boss_join
  restore asked/joined from the branch's `straw-boss` entries
  if joined: rejoin in the background
before_agent_start, first run only, if not joined and not asked:
  section "straw-boss" = prompts/reminder.md ; append entry {asked: true}
every later run: the section is deleted
boss_join (or /boss): join(); on success append {asked: true, joined: true}
```

- The reminder is a system-prompt section for the first run only; pi replays the
  deletion on the next run, so it costs one run.
- `boss_join` is idempotent. The net tools (`boss_status`, `call_tower`,
  `boss_broadcast`) register at join time, so an outside session carries one tool.
- A resumed or reloaded session finds its `straw-boss` entry and rejoins without a
  new entry or a second reminder.

### Main agent: pinning, takeover, handover

Broker ownership follows connection order, so it cannot say who joined first. The
owner is therefore only the **state writer**; who is main is decided by state, and
the owner pins the first joiner.

```text
state (tab channel) = { v: 1, main: <intercom session id>, since: <ms> }
effective main = state.main   if that session is live
               = channel owner otherwise
refresh (serialized; on connection, owner, state, session_left, and after join):
  if state.main is not live: main = owner; if this session is the owner, pin(main = me)
  isMain = (main == me); on change notify the human; write the pane token
```

| Event | What happens |
|---|---|
| Join | Resolve tab and workspace with `herdr pane current`; register the tab channel; wait ≤ 15 s for intercom to connect and ≤ 5 s for an owner; refresh. The first joiner is the owner and pins itself. |
| A session that connected earlier joins later | It becomes the owner (connection order) but `state.main` is live, so the first joiner stays main. |
| `/boss` in a non-owner | `publish({type: "claim"}, {audience: "owner"})`. The owner commits `{main: fromSessionId}`. The claimant waits up to 5 s for itself to become main and reports success or the timeout. |
| `/boss` in the owner | Commits `{main: me}`. |
| `/boss` in a tower | Refused: "This session is the tower, not a main agent". |
| `state` or `owner` change | Each session recomputes; the one that gained the role writes `sb_role=main`, the one that lost it writes `member`. No session writes another's pane. |
| Main exits | An override main leaves: the owner sees `session_left`, finds `state.main` dead, and pins itself. The owner leaves: the broker elects the next eligible session, which finds the stale `state.main` dead and pins itself. |

| Command | Effect |
|---|---|
| `/boss` | Join if needed, then become this tab's main agent. |
| `/boss status` | Shows the `boss_status` result for the human ("Not in the net" for an outside session). |
| `/boss tower` | Joins if needed, opens the workspace's tower if none is live (`ensureTower`), then focuses its tab; the boss typed it, so focus is wanted here. |

### Tower: the dedicated tab

Opening (`ensureTower(workspace)`), run by `call_tower` and `/boss tower` only.
Single-flight per workspace inside one process.

```text
1. Live tower?  workspace token `tower` names a session in listSessions()  → use it
2. Tab labelled `tower` exists?
     root pane runs pi → wait for the token
     root pane is a shell → start pi in that pane (step 4)
3. Otherwise: herdr tab create --workspace W --label tower --cwd C --no-focus --env STRAW_BOSS_ROLE=tower
4. herdr agent start tower-<lowercased W> --kind pi --pane <root_pane> --timeout 30000 -- --name "tower · <label>"
   retried every 0.5 s, at most 20 attempts, only while herdr answers agent_pane_busy
5. Wait ≤ 60 s for the workspace token, then return its session id; on timeout fail with what was done.
```

`C` is the workspace's `worktree.checkout_path` from `herdr workspace list`, or
the caller's cwd.

Tower start, in the tower session. It runs **in the background**, never inside
the `session_start` handler (see Reality anchor):

```text
1. role = tower if STRAW_BOSS_ROLE=tower, or the branch holds a `straw-boss` entry with tower: true;
   on first start append {tower: true, workspaceId}, so a resumed session keeps the role.
2. Wait ≤ 15 s for intercom to connect; fail with the reason and write nothing if it never does.
3. Write pane token sb_role=tower; wait 2 s; list the workspace's panes and sessions.
4. Another tower? Yield if a live session other than me holds the workspace token, or another
   pi pane carries sb_role=tower in a tab whose id sorts lower:
       clear my token, herdr tab close <my tab>
5. Otherwise write workspace token tower=<my id>, register the net tools; refresh both tokens
   every 4 min with a 10 min TTL.
```

Two callers racing in step 3 of opening can each create a tab; step 4 of tower
start closes the extra one before it publishes the token, and callers only send
after the token appears, so no message reaches the yielding tower.

Tower exit: tokens expire within 10 minutes and are cleared at
`session_shutdown`. Readers always check liveness in `listSessions()`, so a stale
token is ignored. There is no automatic respawn (a user who closed the tab is not
fought); the next `call_tower` reopens it and reuses the leftover tab in step 2.

## Roles and injected prompts

### How a session's role is decided

Checked in this order; the first match wins.

| # | Role | Rule | Source |
|---|---|---|---|
| 1 | none | `HERDR_PANE_ID` unset, or `PI_SUBAGENT_ID` set (a worker). The extension returns before registering anything. | env |
| 2 | tower | `STRAW_BOSS_ROLE=tower`, set only by `herdr tab create --env` when the tower tab is opened, or a `straw-boss` entry with `tower: true` on the branch. | env, `appendEntry` |
| 3 | outside | Main-eligible but not joined. Gets the one reminder, `boss_join`, and `/boss`. | session entries |
| 4 | main | Joined, and the effective main of its tab channel. | intercom channel |
| 5 | member | Joined, and another session is the tab's main. | intercom channel |

Roles 1-2 are fixed for the session's life. Roles 3-5 change on join, election,
`/boss` takeover, and handover, all of which arrive as `boss_join`, channel
`owner`, `state`, or `session_left` events.

### Injection

```text
before_agent_start(event):
  role = cachedRole()                     // no herdr or broker call on this path
  text = render(prompts[role]) ; an outside session gets prompts.reminder once, on its first run
  if text: event.systemPromptOptions.sections["straw-boss"] = text
  else:    delete event.systemPromptOptions.sections["straw-boss"]
```

- One section key, `straw-boss`, for every role. A role change replaces its text;
  pi persists only the patch, so an unchanged role costs nothing after the first run.
- The cache (`tab`, `workspace`, `main`, `tower`, `head`) is refreshed by the
  same `listSessions()` and `herdr workspace list` reads that `boss_status` uses,
  after each role event.
- A role change mid-run takes effect at the next run. The extension sends no
  message and starts no turn for it. In the TUI it shows
  `ctx.ui.notify("This session is now the main agent of <tab>")` or the loss of
  the role, for the human only.
- Prompts are read from disk at `session_start`, so an edit applies after
  `/reload`. `{{dir}}` is the extension's prompt directory, for files the model
  reads on demand. A missing value renders as `none yet`.

### Prompt files and budgets

| File | Role | Budget | Carries |
|---|---|---|---|
| `prompts/main.md` | main | ≤ 150 words | What `boss-say` says today, minus the broadcast one-liner, plus the three tools. |
| `prompts/tower.md` | tower | ≤ 150 words | U5, U6, U7, U14, and the reply path (answer with `intercom send`). |
| `prompts/member.md` | member | ≤ 50 words | Who the main agent and tower are, and when to call the tower. |
| `prompts/reminder.md` | outside | ≤ 70 words | The one question of U11 and how to answer it (`boss_join`). |
| `prompts/apps-config.md` | read on demand by a main | unchanged | Moved from `pi/skills/boss-say/references/apps-config.md`. |

There is no worker prompt: workers keep their pi-herdr-agents role prompt and
Straw Boss adds nothing, since the extension does not load in them.

The shipped texts (placeholders `{{tab}}`, `{{workspace}}`, `{{main}}`,
`{{tower}}`, `{{head}}`, `{{dir}}`):

`prompts/main.md` (149 words):

```markdown
You are the main agent of Herdr tab {{tab}}: the boss (the user) works with you here. Your workspace tower is {{tower}}.

- Split work by owning app ({{dir}}/apps-config.md). A task is one worker's end-to-end work in one app; parallel writers in an app each get a worktree; dependent tasks wait.
- Brief each worker in English: required behavior, the Reality anchor, the boss's authorizations quoted; leave cause and location to the worker. End with: "When you need a decision these authorizations do not cover, call `caller_ping` and stop." Answer pings through the boss, then `subagent_resume` the worker.
- Check each result against its brief. Merging to a shared branch or deploying needs the boss's authorization.
- boss_status finds coordinators, call_tower reaches the tower (report coordination friction there), boss_broadcast broadcasts to the net.
- Done when every task has landed or is reported blocked and its worktree is removed.
```

`prompts/tower.md` (150 words):

```markdown
You are the tower of Herdr workspace {{workspace}}; agents talk to you, the boss does not.

Main agents, members, and other towers message you through intercom: answer the sender with intercom send (reply works only for asks).

- Coordinate: route each request to the main agent that owns it, relaying with boss_status, call_tower, and boss_broadcast. Towers coordinate through the head tower, the tower of workspace {{head}}.
- Boss assistant: a friction report gives expected versus actual behavior, the blocked step, and evidence. Find the owner and the broken relationship (registration, endpoint, dependency, shared resource, checkpoint, cleanup); have the owner repair it, read the state back, and have the reporter re-run its step. Return a Straw Boss source defect as a finding with evidence.
- Never ask the boss (no ask_user, robot_hand, focus changes); decisions for the boss go back to the owning main agent.
- Do no app work yourself.
```

`prompts/member.md` (48 words):

```markdown
Straw Boss: you joined the net of tab {{tab}}, whose main agent is {{main}}. The tower of workspace {{workspace}} is {{tower}}. Take shared-resource and collaboration questions to the main agent through intercom. Report coordination friction, such as an agent, endpoint, or shared resource you cannot reach, with call_tower.
```

`prompts/reminder.md` (69 words):

```markdown
Straw Boss: before you start, decide whether your current work competes with other work in this Herdr workspace for resources (ports, databases, files, branches) or needs to collaborate with it. If so, call `boss_join` now; you become the coordinator of this tab, or a member if another session already is. If not, ignore this and do not mention it. You can still call `boss_join` later if the need appears.
```

### Tower lifecycle in its own session

Wakes only on intercom messages (`call_tower`, `boss_broadcast`, replies); idle
sessions get a turn at once, busy ones at the next safe boundary (pi-intercom
`README.md:146`). It opens with `--no-focus` and never focuses a pane or tab.
Messages reach it as plain one-way intercom messages, so it answers with
`intercom send` to the sender, never `intercom reply`.

## Naming and Herdr metadata

All writes use `--source straw-boss`, a 10-minute TTL refreshed every 4 minutes
by one timer per session (cleared at `session_shutdown`), and put the positional
id first.

| Surface | Writer | Value | Coexists with |
|---|---|---|---|
| Tab label of a work tab | not touched | | pi-auto-tab-name owns it. |
| Tab label of the tower tab | the opener, at `tab create` | `tower` | pi-auto-tab-name leaves it: the tower's session name differs and the label is not a bare number (`src/index.ts:160-165`). |
| Herdr agent name of a tower | the opener, at `agent start` | `tower-<lowercased workspace id>` | Names are unique per Herdr server and lowercase only. |
| Pane token `sb_role` | each joined session and tower, for its own pane | `main`, `member`, or `tower` | Pane labels from pi-herdr-agents are not touched. |
| Workspace token `tower` | the tower | its intercom session id | Workspace labels are not touched. |
| Session names | only the tower, once, via `pi --name` | `tower · <workspace label>` | Main sessions keep their names; roles never depend on names. |
| Session entry `straw-boss` | each session | `{asked, joined}` or `{tower, workspaceId}` | Lets a resumed session keep its place. |

## Finding and calling coordinators

| Who asks | How |
|---|---|
| A joined pi session or a tower | `boss_status` tool. |
| A joined pi session or a tower | `call_tower({message, workspace?})`. |
| Claude Code or Codex worker | Read-only: `herdr workspace get "$HERDR_WORKSPACE_ID"` → `.result.workspace.tokens.tower`; `herdr pane list --workspace "$HERDR_WORKSPACE_ID"` → panes with `tokens.sb_role`. To call a running tower: `node ~/.pi/agent/npm/node_modules/pi-intercom/cli.mjs ask --to "$id" --text "<message>"`. Opening a missing tower needs a pi session. |

`boss_status` result (also its `details`):

```ts
{
  me: { id: string; role: "main" | "member" | "tower" };
  workspace: { id: string; label?: string };
  head: string | undefined;                 // id of the first workspace
  tower: { workspace: string; id: string; name: string; head: boolean } | null;
  tabs: Array<{ id: string; label: string; main: string | null; sessions: number }>; // this workspace; ids; joined sessions only
  towers: Array<{ workspace: string; id: string; name: string; head: boolean }>;     // other workspaces
}
```

Built from one `listSessions()`, `herdr pane list` (`sb_role` tokens), and
`herdr workspace list` (`tower` tokens). A token whose session is not live is
dropped. `head` marks the head tower, so a tower sees whom to call for
cross-workspace coordination even when that workspace has no tower yet.

`call_tower({message, workspace?})`:

| Step | Rule |
|---|---|
| Resolve | `workspace` omitted → the caller's; otherwise a workspace id or an exact label from `herdr workspace list`. No match or several matches → error listing the candidates. |
| Find | `ensureTower(W)`; this opens the tower tab when none is live (U4). |
| Deliver | One outbox request `{to: towerId, message}`. The tower answers the caller with `intercom send`. |
| Result | `{workspace, towerId, opened: boolean, status}`; a non-`sent` outbox status is a tool error. |
| Self | A tower calling its own workspace gets an error. |

Tower to tower is `call_tower` with `workspace` set (the head tower when the
topic is cross-workspace coordination), or `boss_broadcast` with scope `towers`.

## `boss_broadcast`

`boss_broadcast({message, scope = "workspace"})`, registered in joined and tower
sessions only (not in outside sessions or workers).

| Scope | Recipients (live sessions from `listSessions()`, minus the sender) |
|---|---|
| `tab` | Joined sessions whose `herdrLocation.tab.id` is the caller's tab. |
| `workspace` | Joined sessions and the tower in the caller's workspace. |
| `towers` | The live tower of every workspace (`sb_role=tower` panes). |
| `all` | Every pi session on the machine: joined or not, workers, and sessions outside Herdr. |

A session counts as joined when its pane carries an `sb_role` token. One outbox
request per recipient, all in parallel, each awaited up to 30 s. The result lists
every recipient with its terminal status; any non-`sent` status makes the call an
error after the others finish. The message is sent once per recipient and never
re-broadcast by receivers (the outbox sends a normal message, not a channel
`capable` publish). Subagents receive only scope `all`; their parent relays.

## Failure behavior

| Condition | Behavior |
|---|---|
| `HERDR_PANE_ID` unset, or a worker | The extension registers nothing. |
| pi-intercom missing | `boss_join` and `/boss` fail with "pi-intercom is not loaded". |
| pi-intercom not connected after 15 s, or a broker without `extension-bus-v1` | Joining and tower start fail with that reason; a tower writes no token. No fallback to name matching. |
| `herdr` command fails | The calling tool or command fails with the command and stderr (an invalid reply names the command too). `agent start` is retried only on `agent_pane_busy`. Token refresh failures are ignored until the next refresh (metadata is display and discovery only; liveness comes from intercom). |
| Pane moved to another tab | The channel stays the launch tab's until `/reload` (channels cannot be unregistered, `index.ts:945`). |
| Tower never publishes its token | `call_tower` fails after 60 s, naming the tower pane; the tab stays open and the next call reuses it. |

## Packaging and install

Following `publishing-pi-extensions`: an extension ships as its own public
repository under `~/projects/<name>`, published to npm as `<name>`.

| Item | Design |
|---|---|
| Package | A new standalone repository and npm package `pi-straw-boss` (D1). Not published from the straw-boss repository: that repository is the Claude Code and Codex plugin with its own version line, while a pi package needs `files` limited to what pi loads. |
| Manifest | `keywords: ["pi-package"]`, `pi.extensions: ["./src/index.ts"]`, `files: ["src", "prompts", "README.md", "LICENSE"]`, `@earendil-works/pi-coding-agent` and `typebox` as `"*"` peer dependencies and pinned dev dependencies (typebox pinned to the version pi-ai nests, 1.3.27, so the types agree). No runtime dependencies; pi-intercom is a runtime requirement checked at join, not an import. |
| Release | The template's `publish.yml` with trusted publishing; the first publish is run by the user (`npm publish --access public --auth-type=web`). |
| weihung-agent-root | Add `"npm:pi-straw-boss@<version>"` to `PACKAGES` in `scripts/pi_root/pins.py`. Remove the Pi install of straw-boss: drop `STRAW_BOSS_GIT` from `local_packages()` (`scripts/pi_root/packages.py:100`) and add `"git:github.com/wayne930242/straw-boss"` to `RETIRED_SOURCES`. `PI_STRAW_BOSS_ROOT` stays only if the Claude Code side still uses it. |
| straw-boss repository | Remove `pi/` and the `pi` block in `package.json`; remove `tests/test_pi_package.py` and `tests/test_pi_skills.py`; the README's Pi section points to the npm package. `CONTEXT.md` gains a **Tower** entry and the Pi meaning of **Boss assistant** (≤ 8 lines). The Claude Code and Codex surfaces stay unchanged. |

## File layout and size

In `~/projects/pi-straw-boss`:

| File | Content | Lines |
|---|---|---|
| `src/index.ts` | Roles, join and reminder, tab channel and pinning, `/boss`, the four tools, prompt injection, token timer, tower start. | 318 |
| `src/herdr.ts` | `herdrRun` over `HERDR_BIN_PATH` with a 5 s timeout (pi-auto-tab-name's shape), typed readers, `report`, `waitFor`, `ensureTower`. | 110 |
| `prompts/*.md` | The prompts above. | 150 / 150 / 50 / 70 words |
| `README.md` | Roles, tools, `/boss`, the Claude Code one-liners, requirements. | |

428 lines of plain TypeScript. The planner's 320-line guide did not survive the
join design (persistence, the reminder, head tower, scoped broadcast) and the four
defects the live check found (each fix is a few lines); the user's direction is
that readable code outranks the cap. Intercom event names and the minimal channel
types are copied as constants, not imported.

## Tests

`npm test` in the new repository (46 tests), against a fake Herdr (workspaces,
tabs, panes, tokens, the CLI subcommands, Herdr's agent-name rules, `agent_pane_busy`)
and a fake intercom broker (owner by connection order, state, outbox, `connected`
and `supported` switches) behind a minimal `ExtensionAPI`; tools are driven through
`execute()` as in `pi-robot-hand/tests/tool.test.ts`.

| # | Case |
|---|---|
| 1 | Outside Herdr and in a worker nothing registers or is injected. |
| 2 | An outside session gets the reminder once (and not after a resume that carries the entry), holds only `boss_join`, has no channel and no tokens. |
| 3 | `wBB:t1` → `straw-boss/tab/7742423a7431` passes the broker regex; a tab id over 24 characters fails with the reason. |
| 4 | The first joiner is main, a later joiner is a member, and the net tools register at join. A session that connected earlier but joins later owns the channel yet the first joiner stays main. |
| 5 | `/boss` from a member publishes a claim, the owner commits, and the two swap pane tokens and prompts at the next run; `/boss` in the owner pins itself; `/boss` in an outside session joins first. |
| 6 | An override main that leaves is cleared; the owner leaves with a stale `state.main` and the new owner pins itself. |
| 7 | A joined session rejoins from its entry on restart without a new entry or reminder. Missing pi-intercom, a disconnected broker, and a broker without `extension-bus-v1` each fail with their reason. |
| 8 | `call_tower` with a live token sends one outbox request; with none it runs `tab create` (`--no-focus --label tower --env STRAW_BOSS_ROLE=tower`), then `agent start` under `tower-<lowercase id>`, then sends after the token appears; a leftover `tower` shell tab is reused; a leftover tab running pi is only waited on and times out with its pane; two racing callers open one tab; `agent_pane_busy` is retried and any other failure is not. |
| 9 | Two towers in one workspace: the higher tab id yields and closes its tab without ever writing the workspace token; an existing live token holder always wins; a tower waits for intercom before writing any token and reports the reason when it never connects. |
| 10 | `session_start` returns promptly even when intercom never connects (regression test for the deadlock; fails when the handler awaits the start). |
| 11 | Broadcast scopes `tab`, `workspace`, `towers` reach only joined sessions and towers; `all` reaches everyone including workers and non-Herdr sessions; the sender is always skipped; one failed recipient fails the call after the rest are reported. |
| 12 | `boss_status` shape, the head tower mark, tower-to-tower calls, workspace resolution by id and label, ambiguity, self-call, and non-`sent` outbox results. |
| 13 | `session_shutdown` stops the timer and clears this session's tokens, idempotently, and a yielding tower never clears the holder's token. |
| 14 | Prompts: word budgets hold, only known placeholders appear, text is plain English, there is no worker prompt. |
| 15 | Boot proof: `tests/imports.test.ts` loads `src/index.ts`, runs the factory, and checks the manifest; the live check below starts it in real pi sessions. |

## Live check (2026-10-17)

Real pi 1.3.0 sessions in real Herdr 0.9.4 with pi-intercom 0.17.1, in two scratch
workspaces. The extension loaded from a project-local `.pi/extensions` file in
`/tmp/pi-straw-boss-live` (already trusted through `/private/tmp`, so towers
started by `herdr agent start` loaded it too). Mains ran `openai/gpt-6-luna`;
towers ran pi's default model. Everything was closed afterwards and checked by PID
and by Herdr listing.

Observed on the final code:

- An outside session quoted the reminder and held only `boss_join`.
- `boss_join` made the first session main (`sb_role=main`, `me.id` equal to the pi
  session id) and the second a member; `/boss` in the member swapped the tokens
  and showed both notices.
- `call_tower` with no tower opened a `tower` tab in 12-13 s without changing the
  focused tab, started `tower-<id>`, published both tokens, and the tower answered
  with `intercom send`.
- `boss_broadcast` scope `workspace` reached the other member and the tower once
  each. Scope `all` was not run live (it would message every real session); the
  unit tests cover it.
- Tower A called workspace B by label: B's tower opened (11 s), received it, and
  answered `pong`.
- A session that quit (`/quit`) had its pane token cleared, and resuming the same
  session file rejoined as a member about 1 s later, with no prompt, no new entry,
  and pi ready in 3 s.

Open items from the first design, resolved:

- Q4, pi started in the new tower tab right away: it works, but 1 of 4 immediate
  starts answered `agent_pane_busy`; `ensureTower` retries that error only.
- Q5, a tower closing its own tab: a duplicate tower yielded within two seconds,
  its tab closed, its pi process exited (the PID that appeared was gone), and the
  holder's workspace token was untouched.

Defects the live check found that the fakes could not (each now has a test):

1. A tower waiting for intercom to connect inside `session_start` blocks
   pi-intercom's own later `session_start`, so intercom never connected. Starting
   (tower or rejoin) now runs in the background.
2. `herdr agent start tower` in a second workspace failed with `agent_name_taken`,
   then the first fix `tower-<id>` failed with `invalid_agent_name` for uppercase
   ids. The name is `tower-<lowercased workspace id>`.
3. `agent_pane_busy` on an immediate start after `tab create` (above).
4. The outbox sends one-way messages, so the tower's `intercom reply` failed; the
   tower prompt says to answer with `intercom send`.

## Decisions (2026-10-17, by the user)

- D1: the package is `pi-straw-boss`.
- D2: broadcasts to workers: subagents receive only scope `all`; `tab`, `workspace`,
  and `towers` skip them and the parent relays. (Supersedes the earlier "every scope".)
- D3: the tower uses pi's default model and thinking.
- D4: joining the net is voluntary (U11); the first joiner of a tab is main.
- D5: the head tower is the tower of the first workspace (U14).
- The smaller open questions take their recommendations: keep `/boss`, a moved
  pane keeps its old tab channel until `/reload`, and a run in progress keeps its
  old role text until the next run.
- A tower TUI dashboard (registered sessions in the workspace, animated workspace
  and subagent status via `ctx.ui.setWidget` and `requestRender`) was deferred to
  v2, in its own file with its own size budget. It shipped in 0.2.0 as
  `src/dashboard.ts`; see "v2 additions (2026-10-17)" below.

## Risks and open questions

| # | Question | Recommendation |
|---|---|---|
| Q1 | `/boss` now that "boss" means the user. | Keep `/boss` (U3); it reads as "the boss picks this session". |
| Q2 | Claude Code and Codex workers cannot open a missing tower from the shell. | Accept in v1; they read the token and ask their main agent otherwise. |
| Q3 | A pane moved between tabs keeps its old tab channel until `/reload`. | Accept; moves are rare and `/reload` fixes it. |
| Q6 | A long run keeps its old role text until the next run starts. | Accept; role changes are rare and the TUI notice tells the human at once. |
| Q7 | A fresh tower once tried an `intercom send` that carried a reply target, was rejected, and retried plainly (tower B's first answer; tower A's went through first time). | Accept; the prompt already says reply works only for asks. Tighten only if it recurs. |

## v2 additions (2026-10-17, pi-straw-boss 0.2.0)

User rules added after the first release, each with its test in the package.

### Sub workspaces act like subagents (U15)

"herdr worktree opens an independent workspace. That is a sub workspace, and a sub
workspace is treated as a subagent: it must not overstep and must not get its own
tower."

| Item | Rule |
|---|---|
| Detection | `herdr workspace list` gives each workspace `worktree: {checkout_path, is_linked_worktree, repo_key, repo_name, repo_root}`. A workspace with `is_linked_worktree: true` is a sub workspace; its parent is the workspace with the same `repo_key` and `is_linked_worktree: false`. |
| Sessions in it | Like workers (U12): no join reminder, no `boss_join`, `/boss` and `/boss tower` refused with the reason, no rejoin on resume, and only scope `all` reaches them. If Herdr cannot say whether the workspace is a sub workspace, the session is barred the same way and says why (fail fast, no guess). |
| Tower | A sub workspace never has one. `call_tower` aimed at it (or issued from it) goes to the parent workspace's tower, opened there on demand; with no open parent workspace it fails with a clear error and opens nothing. |
| Head tower | The tower of the first workspace in list order that is not a sub workspace. |
| Dashboard | Listed under the parent as one line, not as a net. |

### The tower tab is first, and recognised by its marker

- Right after `tab create` (and when a tower adopts a leftover tower tab) the extension moves the tab to index 0 with Herdr's socket API, newline-delimited JSON on `$HERDR_SOCKET_PATH` (default `~/.config/herdr/herdr.sock`): `{"id":"..","method":"tab.move","params":{"tab_id":"..","insert_index":0}}` (`TabMoveParams`, protocol 22). It changes no focus and keeps the tab's `number`. A failed move is a warning notice, never fatal. The CLI has no tab move command.
- The tab is identified by the `sb_role=tower` pane token (written right after `tab create`), not by the label `tower`: a pi-herdr-agents subagent named `tower` also creates a tab with that label in its "tab" and "grouped" pane modes. The label stays display only.

### Tower dashboard

Shown only in a tower session that holds the role and has a UI; read-only, never takes focus.

| Part | Content |
|---|---|
| This net | Joined sessions of the tower's workspace by tab (main first, then members), each with its pi-herdr-agents subagents, then the workspace's sub workspaces. No sessions that did not join, nothing from other workspaces. |
| Other towers | One summary line per workspace with a live tower: label, status, `head tower` mark. |
| States | working = animated spinner (accent), waiting on a question = `?` (warning), idle = `○` (dim), done = `✓` (success), error = `✗` (error); colors from the active pi theme. The title mark is the most urgent state of the net. |
| Cost | 8 fps spinner timer only while something works; 3 s data poll while the widget exists; intercom `presence_update`, `session_joined`, `session_left` poke an early re-read (at most every 0.5 s); `session_shutdown` or losing the role removes the widget and both timers. |

Data sources: pi-intercom `listSessions()` (status, Herdr location), `herdr pane list`
(`sb_role` token, `agent_status` where `blocked` means a question is open, the pi session
file), `herdr workspace list`. A subagent is linked to its parent through pi-herdr-agents'
layout: the parent's session file names `artifacts/<parent session id>/`, and
`subagent-activity/<child id>.json` there is the child's activity record; the child's pane
session file contains the child id (`PI_SUBAGENT_ID` is the same id). Subagents are grouped
under that parent regardless of the tab or workspace their pane sits in (pi-herdr-agents'
"grouped" mode picks a workspace by cwd), and they never count as a net member.
