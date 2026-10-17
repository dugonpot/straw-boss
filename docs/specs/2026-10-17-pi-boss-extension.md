# Pi Straw Boss extension: main agents, towers, and broadcast

Status: design, not implemented. Scope: the Pi side only (`pi/`). The Claude
Code and Codex side (`skills/`, `scripts/`) is untouched.

## Intent

Straw Boss on Pi becomes a thin coordination layer: one extension that replaces
the `boss-say` skill. It registers each session's role, publishes roles in
Herdr, gives every agent one way to find and reach the coordinators, and injects
only that role's short prompt. The extension is glue. It does not track
dispatches, allocate resources, or re-implement anything pi-intercom,
pi-herdr-agents, pi-auto-tab-name, or Herdr's pi integration already does.

User decisions this design follows (translated from the user's answers):

| # | Decision |
|---|---|
| U1 | Every Herdr tab has one work coordinator, the **main agent**. The user stays the **boss**. |
| U2 | Every Herdr workspace has one agent-facing coordinator, the **tower** ("pilots talk to the tower, passengers don't"). |
| U3 | A main agent is chosen automatically, and a session takes over with `/boss`. |
| U4 | The tower is not elected from existing sessions. It lives in its own extra tab, opened when the workspace has none and something needs it. |
| U5 | The tower coordinates agents. The user does not normally talk to it (they may). It does not prompt the user or take focus; decisions for the user go back through the main agent that owns the work. |
| U6 | On Pi the tower also takes the boss assistant role: main agents report Straw Boss coordination friction to it, and it repairs the coordination relationship. There is no separate boss assistant session. |
| U7 | Towers of different workspaces can talk to each other, and any agent has a simple way to call a tower: its own or a named workspace's. |
| U8 | v1 scope: identity, naming, `boss_broadcast`, and calling the tower. Sleep and wake flows come later. |
| U9 | Straw Boss stays drastically lightweight (commit e019d96 removed 436-line `dispatch-recovery.ts`, `pane-balance`, and `pi-dispatch.py` for being too heavy). |
| U10 | The main agent, tower, and worker prompts are injected by code, so Pi needs no skill: `boss-say` retires on Pi and its rules move into the main-agent prompt. Prompts are small markdown files with word budgets (main agent and tower under about 150 words, worker a few lines). Workers keep their pi-herdr-agents role prompt; Straw Boss adds only what it needs. |

## Scope

- In: role identity (main agent, tower, worker), main-agent election and
  `/boss` takeover, the on-demand tower tab, Herdr metadata, the tools
  `boss_status`, `call_tower`, and `boss_broadcast`, the injected role prompts,
  and retiring the Pi `boss-say` skill.
- Out: sleep and wake flows, dispatch tracking, pane layout, model routing,
  renaming sessions, tab labels other than the tower tab, Claude Code or Codex
  changes, cross-machine sessions.

## Vocabulary

| Term | Meaning | Where it lives |
|---|---|---|
| boss | The user. | Identifiers only (`/boss`, `boss_*`), per `CONTEXT.md` "In identifiers, boss means the user". |
| main agent | The coordinator of one Herdr tab. | Owner of the tab's intercom channel, or the `/boss` override in its state. |
| tower | The agent-facing coordinator of one Herdr workspace. Also the boss assistant on Pi. | A pi session in a tab labelled `tower`, published as a workspace token. |
| worker | A pi-herdr-agents subagent (`PI_SUBAGENT_ID` set). | Never a coordinator. |
| member | A main-eligible session in a tab whose main agent is another session. | Gets the worker prompt; becomes main by election or `/boss`. |

## Reality anchor: the APIs this relies on

Every row was read in source or exercised on this machine (pi-intercom 0.17.1,
herdr 0.9.4, pi-auto-tab-name 0.2.0).

| Fact | Evidence |
|---|---|
| Register an extension channel at `session_start` with `{namespace, ownerEligible, onReady, onEvent}`. | pi-intercom `README.md:494-529`, `extension-api.ts:3,80-98`, listener `index.ts:2028-2041` |
| Namespace must match `^[a-z0-9][a-z0-9._/-]{0,63}$`; at most 32 channels per session; a namespace registers once and cannot be unregistered. | `broker/broker.ts:39,1511-1522`; `index.ts:941-956` (duplicate throws at 945) |
| The broker elects one owner per namespace: the eligible session that connected first (`ownerOrder`). Clients cannot seize ownership. When no eligible session remains, the owner is cleared. | `broker/broker.ts:1537-1612` (comment at 1565-1567, empty case 1552-1561) |
| State is ≤ 64 KiB, compare-and-swap, written only by the current owner and epoch; it persists in the broker's state store. | `broker/broker.ts:41,1805-1830`; `index.ts:909-922`; `broker/extension-state.ts:59-66` |
| `publish()` ≤ 16 KiB to audience `owner` or `capable` (the sender is included in `capable`). Any capable session may publish to the owner. | `broker/broker.ts:40,1630-1705`; `README.md:529` |
| Events: `connection`, `owner`, `message`, `state`, `state_result`, `session_joined`, `session_left`, `presence_update`. | `extension-api.ts:70-78`; `index.ts:1437-1490` |
| `listSessions()` returns each live session with `herdrLocation` (workspace id/label, tab id/label, current pane id), freshly resolved per request. | `extension-api.ts:90`; `types.ts:15-31`; `broker/broker.ts:690-707`; `README.md:412`; observed in this session's `intercom list` |
| Extension outbox sends an ordinary intercom message as the current session, one target per request, with a terminal result. `confirmSend` defaults to `false`. | `README.md:531-558`; `extension-api.ts:22-58`; `config.ts:83`; `index.ts:1169` |
| An intercom message wakes an idle session immediately; a busy one gets it at the next safe boundary. Extension-channel traffic never starts a turn. | `README.md:146,496` |
| An unnamed session's intercom name is `subagent-chat-<id>`, so names cannot identify roles. | `index.ts:50,549-556`; this session is listed as `subagent-chat-01a14831-…` |
| `before_agent_start` runs before every run and exposes mutable `systemPromptOptions.sections` (XML-wrapped sections keyed by tag). Changing a section, rather than returning `systemPrompt`, lets Pi append a transcript delta. | pi `dist/core/extensions/types.d.ts:720-742`; `dist/core/system-prompt.d.ts:25-26,52-55`; `docs/extensions.md:104` |
| Later system messages patch `sections` by name, and `null` removes one, so a changed or dropped role section is replayed correctly and earlier messages stay cached. | pi `docs/message-types.md:100-107`; `docs/session-format.md:80` |
| pi-herdr-agents marks workers with `PI_SUBAGENT_ID` and gives them a supervisor channel (`contact_supervisor`). | pi-herdr-agents `maestro/adapters/pi/launch.ts:918,1079`; pi-intercom `index.ts:2194` |
| Extensions start resources in `session_start`, clean up idempotently in `session_shutdown`; `registerTool`, `registerCommand`, `appendEntry`, `pi.events`. | pi `docs/extensions.md:54-60,72-89,225-235` |
| pi-auto-tab-name skips subagents and non-Herdr sessions, names a tab only from its top-left pane, and only when the label is a bare number or one it set. | pi-auto-tab-name `src/index.ts:136-170` |
| `herdr tab create --workspace --label --cwd --env K=V --no-focus` returns `tab` and `root_pane`; the env reaches the pane's shell. | Ran it: `root_pane.pane_id` returned, `echo $STRAW_BOSS_ROLE` printed `tower`; probe tab closed. |
| `herdr agent start <name> --kind pi --pane <id> [--timeout ms] -- <pi args>` starts pi at a shell prompt and waits for readiness. | `herdr agent start --help` |
| `herdr workspace report-metadata <ws> --source --token K=V --ttl-ms` and `herdr pane report-metadata <pane> ...`; tokens read back in `workspace list/get` and `pane list/get`. TTL max 24 h; ≤ 16 tokens per report. | Ran both with a probe token and cleared it; schema `WorkspaceReportMetadataParams`, `PaneReportMetadataParams` |
| Herdr's CLI takes the positional id before options: `report-metadata --source X ... <id>` failed with "unknown option", `report-metadata <id> --source X ...` worked. | Observed on herdr 0.9.4 |
| `herdr pane current` gives this pane's live `tab_id` and `workspace_id`; Herdr's pi integration already reports the agent session (`agent_session.source: herdr:pi`). | Ran `herdr pane current` |
| pi `--name <name>` sets the session display name. | `pi --help` |

## Coordinator model

| | Main agent (tab tier) | Tower (workspace tier) |
|---|---|---|
| Count | One per tab that has an eligible session. | At most one per workspace. |
| Eligible | `HERDR_PANE_ID` set, `PI_SUBAGENT_ID` unset, role is not tower. This is pi-auto-tab-name's rule (`src/index.ts:139`). | Only the session started in the tower tab (role `tower`). |
| Chosen by | Broker election in the tab channel, overridden by `/boss`. | Created on demand; never elected among existing sessions. |
| Intercom | Channel `straw-boss/tab/<hex(tabId)>`, e.g. `wBB:t1` → `straw-boss/tab/7742423a7431`. Hex keeps Herdr's uppercase and `:` inside the namespace regex; tab ids over 24 characters fail fast. | Registers its own tab's channel with `ownerEligible: false` (it needs the channel only for `listSessions`). Session name `tower · <workspace label>`. |
| Herdr | Pane token `sb_role=main`. | Tab label `tower`; pane token `sb_role=tower`; workspace token `tower=<intercom session id>`. |
| Wakes on | The user, its workers, intercom messages. | Intercom messages only: `call_tower`, `boss_broadcast`, replies. |

Every hosted pi session (main, worker, tower) registers exactly one channel: its
tab's. Only main-eligible sessions register it with `ownerEligible: true`.

### Main agent: election, takeover, handover

```text
effective main = state.main   if that session is live
               = channel owner otherwise
state (tab channel) = { v: 1, main?: <intercom session id>, since: <ms> }
```

| Event | What happens |
|---|---|
| Session start | Resolve tab and workspace with `herdr pane current`; register the tab channel. |
| `owner` event | The new owner validates `state.main` against `listSessions()`; a dead id is cleared with `commitState`. |
| `/boss` in a non-owner | `publish({type: "claim"}, {audience: "owner"})`. The owner commits `{main: fromSessionId}`. The claimant waits up to 5 s for a `state` event naming it and reports success or the timeout. |
| `/boss` in the owner | Commits `{main: undefined}` (the owner is main by default). |
| `/boss` in a worker or tower | Refused with the reason; nothing is sent. |
| `state` or `owner` change | Each session recomputes the effective main; the session that gained the role writes its own `sb_role=main` pane token, the one that lost it clears its own. No session writes another's pane. |
| Main exits | Override main leaves: the owner sees `session_left` and clears `state.main`. Owner leaves: the broker elects the next eligible session (`broker.ts:1537-1612`), which validates the state. Last eligible session leaves: no owner; the persisted state is validated by the next owner. |

Takeover rides on state because the broker has no way to force ownership. The
owner is only the state writer; who is main is decided by the state.

| Command | Effect |
|---|---|
| `/boss` | This session becomes its tab's main agent (table above). |
| `/boss status` | Shows `boss_status` for the human. |
| `/boss tower` | Opens the workspace's tower if none is live (`ensureTower`), then focuses its tab; the boss typed it, so focus is wanted here. |

### Tower: the dedicated tab

Opening (`ensureTower(workspace)`), run by `call_tower` and `/boss tower` only.
Single-flight per workspace inside one process.

```text
1. Live tower?  workspace token `tower` names a session in listSessions()  → use it
2. Tab labelled `tower` exists?
     root pane runs pi → wait for the token
     root pane is a shell → herdr agent start (step 4) in that pane
3. Otherwise: herdr tab create --workspace W --label tower --cwd C --no-focus --env STRAW_BOSS_ROLE=tower
4. herdr agent start tower --kind pi --pane <root_pane> --timeout 30000 -- --name "tower · <label>"
5. Wait ≤ 60 s for the workspace token, then return its session id; on timeout fail with what was done.
```

`C` is the workspace's `worktree.checkout_path` from `herdr workspace list`, or
the caller's cwd.

Tower start, in the tower session:

```text
1. role = tower if STRAW_BOSS_ROLE=tower, or the branch holds a `straw-boss-role` entry;
   on first start appendEntry("straw-boss-role", {role: "tower", workspaceId}) so a resumed session keeps the role.
2. Write pane token sb_role=tower; wait 2 s; list the workspace's panes.
3. Another live pane carries sb_role=tower?
     it already holds the workspace token, or its tab id sorts lower → yield:
       clear my token, herdr tab close <my tab>
4. Otherwise write workspace token tower=<my id>; refresh both tokens every 4 min with a 10 min TTL.
```

Two callers racing in step 3 of opening can each create a tab; step 3 of tower
start closes the extra one before it publishes the token, and callers only send
after the token appears, so no message reaches the yielding tower. This also
covers callers in other workspaces, so no lock channel is needed.

Tower exit: tokens expire within 10 minutes and are cleared at
`session_shutdown`. Readers always check liveness in `listSessions()`, so a
stale token is ignored. There is no automatic respawn (a user who closed the tab
is not fought); the next `call_tower` reopens it and reuses the leftover tab in
step 2.

## Roles and injected prompts

### How a session's role is decided

Checked in this order; the first match wins.

| # | Role | Rule | Source |
|---|---|---|---|
| 1 | none | `HERDR_PANE_ID` unset. Nothing registers and nothing is injected. | env |
| 2 | tower | `STRAW_BOSS_ROLE=tower`, set only by `herdr tab create --env` when the tower tab is opened, or a `straw-boss-role` entry on the branch (written on the tower's first start, so resume and Herdr restore keep the role). | env, `appendEntry` |
| 3 | worker | `PI_SUBAGENT_ID` set by pi-herdr-agents. | env |
| 4 | main | This session is the effective main of its tab channel (`state.main` if live, else the channel owner). | intercom channel |
| 5 | member | Any other hosted session: a main-eligible session in a tab whose main is another session. Gets the worker prompt. | intercom channel |

Roles 1-3 are fixed for the session's life. Roles 4 and 5 swap on election,
`/boss` takeover, and handover, all of which arrive as channel `owner`,
`state`, or `session_left` events.

### Injection

```text
before_agent_start(event):
  role = cachedRole()                     // no herdr or broker call on this path
  text = render(prompts[role], {tab, workspace, main, tower, dir})
  if text: event.systemPromptOptions.sections["straw-boss"] = text
  else:    delete event.systemPromptOptions.sections["straw-boss"]
```

- One section key, `straw-boss`, for every role. A role change replaces its
  text; losing every role removes it. Pi persists only the patch
  (`docs/message-types.md:100-107`), so an unchanged role costs nothing after
  the first run.
- The cache is refreshed by channel events and, for the tower and main names,
  by the same `listSessions()` and `herdr workspace get` reads that
  `boss_status` uses, run at `session_start` and after each role event.
- A role change mid-run takes effect at the next run's `before_agent_start`.
  The extension sends no message and starts no turn for it. In the TUI it
  shows `ctx.ui.notify("This session is now the main agent of <tab>")` or the
  loss of the role, for the human only.
- Prompts are read from disk at `session_start`, so an edit applies after
  `/reload`. `{{dir}}` is the extension's prompt directory, for files the model
  reads on demand.

### Prompt files and budgets

| File | Role | Budget | Carries |
|---|---|---|---|
| `prompts/main.md` | main | ≤ 150 words | What `boss-say` says today, minus the broadcast one-liner, plus the three tools. |
| `prompts/tower.md` | tower | ≤ 150 words | U5, U6, U7. |
| `prompts/worker.md` | worker, member | ≤ 50 words | Who the main agent and tower are, and when to call the tower. Nothing pi-herdr-agents already gives a worker (role, brief, `contact_supervisor`, `caller_ping`). |
| `prompts/apps-config.md` | read on demand by a main | unchanged | Moved from `pi/skills/boss-say/references/apps-config.md`. |

Drafts. Placeholders are `{{tab}}`, `{{workspace}}`, `{{main}}`, `{{tower}}`,
and `{{dir}}`; a missing value renders as `none yet`.

`prompts/main.md` (150 words):

```markdown
You are the main agent of Herdr tab {{tab}}: the boss (the user) works with you here. Your workspace tower is {{tower}}.

- Split work by owning app ({{dir}}/apps-config.md). A task is one worker's end-to-end work in one app; parallel writers in one app each get a worktree; dependent tasks wait.
- Brief each worker in English: required behavior, the Reality anchor, and the boss's authorizations quoted; leave cause and location to the worker. End with: "When you need a decision these authorizations do not cover, call `caller_ping` and stop." Answer pings through the boss, then `subagent_resume` the worker.
- Check each result against its brief. Merging to a shared branch or deploying needs the boss's authorization for that target.
- boss_status finds coordinators, call_tower reaches the tower (report coordination friction there), boss_broadcast broadcasts.
- Done when every task has landed or is reported blocked and its worktree is removed.
```

`prompts/tower.md` (149 words):

```markdown
You are the tower of Herdr workspace {{workspace}}. Agents talk to you; the boss (the user) normally does not.

Main agents (one per tab), workers, and other towers reach you through intercom; answer with intercom reply.

- Coordinate: route each request to the main agent that owns it, relay between main agents and towers, and use boss_status, call_tower, and boss_broadcast.
- Boss assistant: a friction report states expected versus actual behavior, the blocked step, and evidence. Find the owner and the broken relationship (registration, endpoint, dependency, shared resource, checkpoint, cleanup); have that owner repair it, read the state back, and have the reporter re-run its blocked step. Return a Straw Boss source defect to the reporter as an evidenced finding.
- Never ask the boss: no ask_user, robot_hand, or focus changes. Decisions for the boss go back to the owning main agent.
- Do not do app work yourself.
```

`prompts/worker.md` (42 words):

```markdown
Straw Boss: the main agent of tab {{tab}} is {{main}}; the tower of workspace {{workspace}} is {{tower}}. Questions about your task go where your brief says. Report coordination friction, such as an agent, endpoint, or shared resource you cannot reach, with call_tower.
```

### Tower lifecycle in its own session

Wakes only on intercom messages (`call_tower`, `boss_broadcast`, replies);
idle sessions get a turn at once, busy ones at the next safe boundary
(pi-intercom `README.md:146`). It opens with `--no-focus` and never focuses a
pane or tab.

## Naming and Herdr metadata

All writes use `--source straw-boss`, a 10-minute TTL refreshed every 4 minutes
by one timer per session (cleared at `session_shutdown`), and put the positional
id first.

| Surface | Writer | Value | Coexists with |
|---|---|---|---|
| Tab label of a work tab | not touched | | pi-auto-tab-name owns it. |
| Tab label of the tower tab | the opener, at `tab create` | `tower` | pi-auto-tab-name leaves it: the tower's session name differs and the label is not a bare number (`src/index.ts:160-165`); it also skips model titles for named sessions. |
| Pane token `sb_role` | each session, for its own pane | `main` or `tower` | Pane labels from pi-herdr-agents are not touched. |
| Workspace token `tower` | the tower | its intercom session id | Workspace labels are not touched. |
| Session names | only the tower, once, via `pi --name` | `tower · <workspace label>` | Main sessions keep their names; roles never depend on names. |

## Finding and calling coordinators

| Who asks | How |
|---|---|
| Any pi session | `boss_status` tool. |
| Any pi session | `call_tower({message, workspace?})`. |
| Claude Code or Codex worker | Read-only: `herdr workspace get "$HERDR_WORKSPACE_ID"` → `.result.workspace.tokens.tower`; `herdr pane list --workspace "$HERDR_WORKSPACE_ID"` → panes with `tokens.sb_role`. To call a running tower: `node ~/.pi/agent/npm/node_modules/pi-intercom/cli.mjs ask --to "$id" --text "<message>"`. Opening a missing tower needs a pi session. |

`boss_status` result (also its `structuredContent`):

```ts
{
  me: { id: string; role: "main" | "tower" | "worker" | "session" };
  workspace: { id: string; label: string };
  tower: { id: string; name: string; paneId: string } | null;
  tabs: Array<{ id: string; label: string; main: { id: string; name: string } | null; sessions: number }>;
  towers: Array<{ workspace: { id: string; label: string }; id: string }>; // other workspaces
}
```

Built from one `listSessions()` (live sessions and their locations), `herdr pane
list --workspace W` (`sb_role` tokens), and `herdr workspace list` (`tower`
tokens). A token whose session is not live is dropped.

`call_tower({message, workspace?})`:

| Step | Rule |
|---|---|
| Resolve | `workspace` omitted → the caller's; otherwise a workspace id or an exact label from `herdr workspace list`. No match or several matches → error listing the candidates. |
| Find | `ensureTower(W)`; this opens the tower tab when none is live (U4). |
| Deliver | One outbox request `{to: towerId, message}`. The tower replies to the caller through intercom. |
| Result | `{workspace, towerId, opened: boolean, status}`; a non-`sent` outbox status is a tool error. |
| Self | A tower calling its own workspace gets an error. |

Tower to tower is `call_tower` with `workspace` set, or `boss_broadcast` with
scope `towers`.

## `boss_broadcast`

`boss_broadcast({message, scope = "workspace"})`, registered in main and tower
sessions only (not in workers).

| Scope | Recipients (live sessions from `listSessions()`, minus self) |
|---|---|
| `tab` | Sessions whose `herdrLocation.tab.id` is the caller's tab. |
| `workspace` | Sessions in the caller's workspace, including its tower. |
| `towers` | The live tower of every workspace (`tower` tokens). |
| `all` | Every session, including those outside Herdr. |

One outbox request per recipient, all in parallel, each awaited up to 30 s. The
result lists every recipient with its terminal status; any non-`sent` status
makes the call an error after the others finish. The message is sent once per
recipient and never re-broadcast by receivers (the outbox sends a normal
message, not a channel `capable` publish).

## Failure behavior

| Condition | Behavior |
|---|---|
| `HERDR_PANE_ID` unset | Registers nothing; tools return "not running inside Herdr". |
| pi-intercom missing, disconnected, or broker without `extension-bus-v1` | Tools and `/boss` fail with that reason. No fallback to name matching. |
| `herdr` command fails | The calling tool or command fails with the command and stderr. Token refresh failures are ignored until the next refresh (metadata is display and discovery only; liveness comes from intercom). |
| Pane moved to another tab | The channel stays the launch tab's until `/reload` (channels cannot be unregistered, `index.ts:945`). |

## Packaging and install

Following `publishing-pi-extensions`: an extension ships as its own public
repository under `~/projects/<name>`, published to npm as `<name>`.

| Item | Design |
|---|---|
| Package | A new standalone repository and npm package (recommended name `pi-straw-boss`; the user picks the name, see D1). Not published from the straw-boss repository: that repository is the Claude Code and Codex plugin with its own version line, while a pi package needs `files` limited to what pi loads. |
| Manifest | `keywords: ["pi-package"]`, `pi.extensions: ["./src/index.ts"]`, `files: ["src", "prompts", "README.md", "LICENSE"]`, `@earendil-works/pi-coding-agent` as a `"*"` peer dependency and a pinned dev dependency. No runtime dependencies; pi-intercom is a runtime requirement checked at `session_start`, not an import. |
| Release | The template's `publish.yml` with trusted publishing; the first publish is run by the user (`npm publish --access public --auth-type=web`). |
| weihung-agent-root | Add `"npm:<name>@<version>"` to `PACKAGES` in `scripts/pi_root/pins.py`. Remove the Pi install of straw-boss: drop `STRAW_BOSS_GIT` from `local_packages()` (`scripts/pi_root/packages.py:100`) and add `"git:github.com/wayne930242/straw-boss"` to `RETIRED_SOURCES`. `PI_STRAW_BOSS_ROOT` stays only if the Claude Code side still uses it. |
| straw-boss repository | Remove `pi/` and the `pi` block in `package.json`; remove `tests/test_pi_package.py` and `tests/test_pi_skills.py`; the README's Pi section points to the npm package. The Claude Code and Codex surfaces stay unchanged. |

## File layout and size budget

In the new repository:

| File | Content | Budget |
|---|---|---|
| `src/index.ts` | Role detection, tab channel and election, `/boss`, the three tools, prompt injection, token timer. | ≤ 230 lines |
| `src/herdr.ts` | `run(args)` over `HERDR_BIN_PATH` with a 5 s timeout (pi-auto-tab-name's shape), JSON parsing, `ensureTower`. | ≤ 90 lines |
| `prompts/main.md`, `prompts/tower.md`, `prompts/worker.md` | The role prompts above. | 150 / 150 / 50 words |
| `prompts/apps-config.md` | Moved unchanged from `pi/skills/boss-say/references/`. | |
| `README.md` | Roles, tools, `/boss`, the Claude Code one-liners, requirements (pi-intercom ≥ 0.17.1, herdr ≥ 0.9.4). | |

Hard cap: 320 lines of TypeScript. Intercom event names and the minimal channel
types are copied as constants, not imported. In straw-boss, `CONTEXT.md` gains
a **Tower** entry and the Pi meaning of **Boss assistant** (≤ 8 lines).

## Tests

`npm test` in the new repository, with an injected Herdr runner (as
pi-auto-tab-name takes `run`, `src/index.ts:136`) and a fake intercom bus on
`pi.events`; tools are driven through `execute()` against a minimal
`ExtensionAPI`, as in `pi-robot-hand/tests/tool.test.ts`.

| # | Case |
|---|---|
| 1 | A worker registers `ownerEligible: false` and gets no `boss_broadcast`; outside Herdr nothing registers or is injected. |
| 2 | `wBB:t1` → `straw-boss/tab/7742423a7431` passes the broker regex; a 25-character tab id fails. |
| 3 | `/boss` from a non-owner publishes a claim; the owner commits; the new main writes `sb_role=main` and the old one clears its own. |
| 4 | The override main leaves → cleared; the owner leaves with a stale `state.main` → the new owner clears it. |
| 5 | `call_tower` with a live token sends one outbox request; with none it runs `tab create` with `--no-focus --label tower --env STRAW_BOSS_ROLE=tower`, then `agent start`, then sends after the token appears; with a leftover `tower` shell tab it reuses that pane. |
| 6 | Two towers in one workspace: the one with the higher tab id closes its tab; an existing token holder always wins. |
| 7 | Broadcast scopes `tab`, `workspace`, `towers`, `all` select the right recipients and skip self; one failed recipient fails the call after the rest are reported. |
| 8 | Injection: each role gets exactly its file under the `straw-boss` key; a takeover swaps main and member text at the next `before_agent_start`; a session that loses every role has the key removed; the tower keeps its prompt after resume from the `straw-boss-role` entry. |
| 9 | Prompt files: word budgets hold, only known placeholders appear, and the text is English. |
| 10 | `session_shutdown` stops the timer and clears this session's tokens, idempotently. |
| 11 | Boot proof: `tests/imports.test.ts` loads `src/index.ts` and runs the factory; the tmux run from the publishing skill (`pi --no-session -ne -e src/index.ts`) starts past registration. |

Live check in Herdr, after the suite passes: two pi sessions in one tab →
`boss_status` names the first as main; `/boss` in the second swaps it and the
next run of each shows the swapped prompt; a main calls `call_tower` → a `tower`
tab opens without taking focus, the tower receives the message and replies; a
tower in a second workspace answers a tower-to-tower call; `boss_broadcast` with
scope `workspace` reaches every other session once.

## Decisions (2026-10-17, by the user)

- D1: the package is `pi-straw-boss`.
- D2: broadcasts reach workers in every scope.
- D3: the tower uses pi's default model and thinking.
- The smaller open questions below take their recommendations: keep `/boss`, a moved pane keeps its old tab channel until `/reload`, and a run in progress keeps its old role text until the next run.
- A tower TUI dashboard (registered sessions in the workspace, animated workspace and subagent status via `ctx.ui.setWidget` and `requestRender`) is deferred to v2, in its own file with its own size budget.

## Risks and open questions

| # | Question | Recommendation |
|---|---|---|
| Q1 | `/boss` now that "boss" means the user. | Keep `/boss` (U3); it reads as "the boss picks this session". |
| Q2 | Claude Code and Codex workers cannot open a missing tower from the shell. | Accept in v1; they read the token and ask their main agent otherwise. |
| Q3 | A pane moved between tabs keeps its old tab channel until `/reload`. | Accept; moves are rare and `/reload` fixes it. |
| Q4 | `herdr agent start` readiness right after `tab create` is not yet exercised (only `pane run` was). | Test 5 and the live check cover it; on timeout the tool fails and reports the opened tab. |
| Q5 | Does `herdr tab close` on its own tab end the yielding tower cleanly? | Verify in the live check; the token is cleared before the close either way. |
| Q6 | A long run keeps its old role text until the next run starts. | Accept; role changes are rare and the TUI notice tells the human at once. |
