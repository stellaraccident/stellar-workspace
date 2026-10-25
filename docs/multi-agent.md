# Named agents, beads, and shared machine work

This is the living design and operator reference for Stellar Workspace's opt-in
team support. Update it alongside changes to behavior. Implemented 2026-10-25;
Codex is the supported managed client. Pi and omp adapters remain future work.
Claude support has been removed.

## The operating model

Each workspace has one beads-rust tracker and a roster of named workers. Each
worker has a persistent Codex conversation, a native interactive terminal UI in
tmux, and a small Python controller. The controller polls local state; idle
workers make no model calls. Ready assignments and changed MOTDs trigger targeted
`codex queue` messages addressed to the recorded thread UUID and private backend.
There is no terminal typing automation, batch-exec loop, or custom transcript UI.

Start with `lead`, coders `ada` and `grace`, reviewer `lin`, and a machine-wide
`it` agent. Names and roles live in `workspace.toml`; edit the roster before
running `sw-init --team` to generate instructions for additional names. Roles are
`lead`, `coder`, `reviewer`, and `it`. Names are lowercase identifiers, up to 32
characters. The default lead starts in human mode; other workers start in auto.
Starting is explicit and runs from the external operator shell. A sandboxed lead
coordinates tasks; it does not launch nested supervisors. An ordinary operator
Codex session outside the sandbox can run those same start commands when asked.

Keep task state and handoffs in beads, source changes in Git, review feedback in
Git notes through `sw-review`, and current operational announcements in MOTD.
A bead assignment authorizes bounded work; it does not itself start a process.

## Bootstrap

```bash
# Before creating a venv, or use installed sw-init --team in an existing workspace:
python3 /path/to/stellar-workspace/sw-init.py /path/to/workspace --team
cd /path/to/workspace
direnv allow                         # human, after reviewing .envrc
python -m pip install /path/to/stellar-workspace
sw-agent install-br --dry-run
sw-agent install-br
sw-agent init-beads
sw-agent doctor
```

Dependencies are Linux, working Bubblewrap/user namespaces, tmux, Codex with
native `queue`, Unix App Server and remote resume support, plus beads-rust
**0.7.6**. The implementation was exercised with Codex **0.162.1** and the actual
br 0.7.6 release. Codex APIs are experimental; qualify upgrades using the native
integration tests rather than assuming compatibility from a version number.
`doctor` checks the selected br, Codex queue support, tracker and shared setup.

`sw-init --team` creates configuration, local notices, role/name instructions and
team/machine skills. It works without third-party Python packages, never starts
agents, and never creates or migrates a tracker. Normal repair/upgrade provenance
rules apply. Edited notices and instructions are preserved; conflicting upgrades
require manual reconciliation. Runtime state is ignored by Git.

`install-br` downloads a pinned Linux musl x86_64/aarch64 release, verifies its
embedded SHA-256, and creates `programs/br/bin/br`. It refuses overwriting a binary.
Alternatively configure `team.br` with a qualified existing installation.
`init-beads` refuses an existing `.beads`; no old review commits or beads-specific
review metadata are migrated. Existing trackers require deliberate operator
inspection and migration. Preserve their databases, journals and exports before
upgrading; there is no automatic JSONL recovery.

## How you interact as operator

```bash
for name in lead ada grace lin; do sw-agent start "$name"; done
sw-agent visit lead
```

Talk normally: “Create beads for these two tasks, assign Ada and Grace, and arrange Lin's review.” The installed instructions explain the commands
and boundaries to the lead. Starting workers once is operator setup; each task
assignment thereafter wakes the appropriate running worker automatically. You can keep this conversation open as your main
interface; use the shell commands whenever that is more convenient.

```bash
sw-agent start ada           # idempotent while its controller is running
sw-agent visit ada           # native Codex UI; switches pickup to human mode
sw-agent watch ada           # read-only tmux attachment; pickup mode unchanged
sw-agent send ada 'Report your progress and park at the next safe checkpoint.'
sw-agent pause ada           # suspend new automatic task pickup
sw-agent auto ada            # explicitly return scheduling to automation
sw-agent status
sw-agent logs ada            # backend diagnostics, not the conversation UI
sw-agent stop ada --after-task
sw-agent stop ada
```

Detach tmux using its normal prefix then `d`; the worker keeps running. Detach
does **not** resume automation. `visit` takes scheduling control before attaching;
`auto` explicitly returns it. Native Codex input supports discussion, follow-ups,
steering and interruption in the same conversation. `send` queues a follow-up;
it does not promise immediate mid-tool interruption. Already queued work cannot
be recalled by pause, so the wake prompt tells the agent to recheck its mode.
Human input takes priority by instruction.

`--after-task` waits for the current Codex turn to become idle, not for an entire
multi-turn bead to finish. Immediate stop terminates the sandboxed backend; it
cannot promise rollback of a running tool. Normal stop removes the owned tmux
session and private sockets. Conversation history remains in the agent's state,
and a subsequent start resumes its UUID and scheduling mode. If an active bead survived shutdown,
restart enters `needs-human` to prevent silent reclamation. Inspect the bead and
files, give recovery instructions, then explicitly choose `auto` when appropriate.

A tmux session left after a controller crash is retained for inspection. Inspect
its controller window and backend log before removing that exact session and
restarting. There is no automatic restart after a crash or reboot. If you quit
the native UI, stop/start the worker to reopen it; detach when you merely want
to leave it working. Never attach a second independent scheduler to these workers.

## Tasks, claims, and handoffs

```bash
sw-agent beads create 'Investigate GPU regression' --assignee ada --json
sw-agent assign sw-EXAMPLE ada
sw-agent beads ready --assignee ada --json
# Inside Ada's managed session (SW_AGENT=ada):
sw-agent claim sw-EXAMPLE
sw-agent beads comments add sw-EXAMPLE 'Findings, changed files, tests and next steps...'
sw-agent checkpoint --state review --bead sw-EXAMPLE
```

`sw-agent beads` supplies the workspace's canonical `BEADS_DIR` even from another
checkout, and the stable agent actor when `SW_AGENT` is set. A small `br` adapter
inside each worker also supplies its actor. The wrapper removes inherited tracker
routing variables. Do not create independent trackers in worktrees.

The watcher considers only open, dependency-ready beads assigned to that exact
name. It excludes `motd`, `sw:awaiting-review`, and `sw:needs-human` labels. A wake
lists ready IDs; the agent must inspect and claim one through `sw-agent claim`.
Claim rechecks readiness and uses `--if-unchanged` against `updated_at` and the
correct actor. It records the active bead locally. Never reclaim another agent's
in-progress work just because a controller looks stale.

A fingerprint of ready IDs/timestamps prevents repeated wakes when the model
parks without claiming. Explicit `auto` clears this fingerprint. A recorded
in-progress bead prevents further automatic pickup until a handoff/checkpoint or
bead state change. The controller schedules; the agent performs and records work.

Checkpoint states are `working`, `waiting`, `review`, and `needs-human`. Waiting
and review release the local active-bead gate; needs-human suspends automation.
They do not change br task status or labels. Before handing off, add concrete
findings, paths, checks, limitations and next action to the bead; close completed
work or add an appropriate exclusion label to prevent unintended pickup. Assign
review work to Lin through beads, use Git notes for feedback, and obtain human
permission for root commits, merges and pushes. Use dependencies for ordered work.

## Personal areas and cooperative boundaries

| Path | Ownership and purpose |
| --- | --- |
| `agents/roles/ROLE.md` | Tracked role instructions |
| `agents/NAME/AGENTS.md` | Tracked name, role and ownership instructions |
| `agents/NAME/{build,cache,tmp,scratch,programs,logs,state}/` | Ignored personal outputs, diagnostics and Codex history/auth |
| `.sw/agents/NAME/` | Ignored locks, PID identity, thread UUID, mode, active bead and notice receipts |
| `worktrees/` | Independent task checkouts, created deliberately by agents |
| `.beads/` | One tracker for the workspace |
| `MOTD.md` | Workspace notices |

Workers start in their personal area. Use explicit worktree paths under it or
under `worktrees/`, task branches and separate build directories. Do not switch
branches in a peer's checkout. Preserve dirty work. Visiting another agent's area
requires human or owning-peer permission, including an assigned triage bead.
The workspace venv is shared for installed tools; serialize package changes.

These are cooperative instructions, not security isolation between peers. Workers
can access the workspace and its writable state. Host credential isolation is a
separate mandatory boundary.

```toml
[team]
shared_root = "~/agent-shared"
codex = "codex"                   # executable or explicit path
br = "programs/br/bin/br"
poll_seconds = 5                  # 1..300

[team.agents.ada]
role = "coder"
# model = "YOUR_MODEL"            # optional; otherwise Codex local default
# gpu = false                    # optional override of sandbox.gpu
shared_ro = []
shared_rw = []
```

GPU access inherits `sandbox.gpu` (on by default); configure `--no-gpu`/false for
machines without the required AMD devices. This iteration has no GPU resource
scheduler or enforced reservation system. Agents coordinate experiments and
maintenance through beads, notices and explicit permission.

## Shared machine and IT workspace

Shared initialization is a separate explicit action:

```bash
sw-agent init-shared --path ~/agent-shared --dry-run
sw-agent init-shared --path ~/agent-shared
cd ~/agent-shared/it
# Review .envrc, activate its own direnv venv, install stellar-workspace as above.
sw-agent install-br
sw-agent init-beads
sw-agent --machine start it
sw-agent --machine visit it
```

It creates `models/`, `rocm/`, `manifests/`, `staging/`, `control/workspaces/`,
`MOTD.md`, and an independent `it/` workspace with its own venv, tracker and agent
state. The marker `control/stellar-shared.json` identifies initialized shared
state. Existing notices/data are preserved; arbitrary existing IT/control state
is not silently adopted. Repeat initialization preserves the installation.
Project `[team].shared_root` must point to the same location. `--machine` redirects
commands from a project workspace to this IT workspace; `--workspace PATH` selects
an explicit project. Both scope flags work before or after a subcommand.

Project workers get machine MOTD and control metadata read-only. Other shared
paths are opt-in `shared_ro`/`shared_rw` entries, relative to shared_root. For
example `shared_ro = ["models", "rocm"]` permits using those installations when
asked. Configure mounts before start; restart to apply changes. Shared-root
symlink escapes, protected mounts and known credential paths are rejected.
The explicit IT initialization grants IT writes to notices, control, models,
ROCm, manifests and staging. It grants no host package administration authority.
IT should stage changes, publish exact paths/versions and verify them before
promotion. Host drivers, reboots, service changes and destructive cleanup require
human permission.

Starting a worker registers its workspace in the shared registry. Inspect
`sw-agent status --all-workspaces` or `sw-agent motd status --all-workspaces` for
known workers and receipts. Stopped/stale entries are visible as such; the
registry is local metadata, not service discovery or a remote control plane.

## Broadcasts and maintenance

Edit workspace `MOTD.md` for local notices or shared `MOTD.md` for machine-wide
announcements. Use current facts: owner, affected resources, requested action,
expiry/clear condition. Keep secrets out of notices. Active controllers hash both
files and queue each changed revision once, including in human/paused mode.
Inside managed sandboxes, `sw-agent motd` reads the controller snapshot so atomic
host file replacements cannot leave notice commands stuck on an old bind-mounted
inode. Stopped workers receive current notices through their instructions/checkpoints
when resumed; there is no delivery while their controller is stopped.

```bash
sw-agent motd
# In a named session, after reading and acting at a safe checkpoint:
sw-agent motd ack CURRENT_HASH
sw-agent motd status --all-workspaces
sw-agent maintenance request --reason 'IT: drain GPU work before ROCm validation'
sw-agent maintenance status
sw-agent maintenance release --reason 'IT: validation complete; resume pickup'
```

A changed notice is queued; it does not forcibly interrupt tools. Receipts record
an explicit acknowledgement of the current hash (at least its first 12 characters).
A receipt is not proof that a GPU is free. Human/IT must inspect acknowledgements,
active tasks and actual processes before disruptive maintenance.

The maintenance flag pauses **all new automatic bead pickup**, including CPU
work, across configured workspaces. Existing tasks, manual work and MOTD delivery
continue. This deliberately simple cooperative gate is not a hardware lock,
drain implementation, interrupt mechanism or global stop button. IT/human publish
the notice separately and explicitly release maintenance afterward.

## Runtime and credential boundary

The backend always runs inside `sw-sandbox`'s Bubblewrap plan, with rebuilt
environment, synthetic home, the workspace venv, and personal `/tmp`/cache/state.
Only selected Codex provider `auth.json` seeds its state; host Codex configuration,
shell snapshots and existing sessions are excluded for named workers. Auth refresh
and history persist locally. Provider credentials are intentionally available;
GitHub and PyPI machine credentials are excluded. GitHub writes remain outside
the read-only bridge's policy. Agent instructions reinforce that boundary.

The controller and native UI run outside Bubblewrap and connect only to the
recorded worker endpoint. They use a minimal environment and never execute
model-supplied host commands. Codex's Unix rendezvous implementation uses a
reserved daemon directory; each backend receives its own private directory,
and the controller translates that worker's socket alias. Host Codex daemon
sockets are never mounted. No unrestricted host-backend fallback is allowed.
Locks prevent duplicate controllers; PID start-time identity guards against PID
reuse. Status/control commands inside a worker use a recent controller heartbeat
because host PIDs differ in its namespace; this is a cooperative liveness view.
There is no network listener, daemon service or inference when idle.

Filesystem confinement between agents is not promised. The existing default
`sw-sandbox -- codex` mode still shares host Codex state; managed named agents
always select the isolated Codex profile. Do not confuse the two modes.

## Validation and next iterations

Pytest covers primordial setup, idempotence/repair, custom-file preservation,
roster validation, actor/routing/conditional claims, singleton locks, mode changes,
wake deduplication, maintenance gates, MOTD hashes and credential rejection.
Linux sandbox tests inspect GitHub and PyPI token invisibility, including named
Codex profiles. Packaging tests exercise installed entry points and templates.

Native integration tests use the actual Codex binary, a disposable local fake
Responses provider, private tmux server, real br and Bubblewrap. They verify native
UI output, typed human input during an active turn, later queued work in the same
thread, idle without inference, human-mode suspension, notices and shutdown.
No production credentials or paid model calls are used. Set `SW_TEST_BR` to a
qualified br 0.7.6 binary; optionally `SW_TEST_CODEX` selects Codex. Missing
external tools skip the corresponding tests, so inspect the reported skips.

Future work: qualify native interactive pi/omp adapters, improve crash/reconnect
UX, richer peer mail if bead comments become insufficient, and GPU reservations
if cooperative maintenance proves inadequate. NTM or coworkers' orchestration
may replace the controller later; the names, beads, directories and notices should
remain usable. Avoid growing a competing general-purpose scheduler here.

Research references, checked 2026-10-25:

- [Codex CLI](https://learn.chatgpt.com/docs/cli/reference),
  [queue/developer commands](https://learn.chatgpt.com/docs/developer-commands),
  [App Server](https://learn.chatgpt.com/docs/app-server),
  [interactive prompting](https://learn.chatgpt.com/docs/prompting).
- [beads-rust v0.7.6](https://github.com/Dicklesworthstone/beads_rust/tree/v0.7.6)
  and [release notes](https://github.com/Dicklesworthstone/beads_rust/releases/tag/v0.7.6).
- [pi RPC](https://github.com/earendil-works/pi/blob/main/packages/coding-agent/docs/rpc.md)
  and [omp RPC](https://github.com/can1357/oh-my-pi/blob/main/docs/rpc.md);
  RPC support alone does not establish native TUI/watcher coexistence.
- [NTM](https://github.com/Dicklesworthstone/ntm) and
  [Agent Mail Rust](https://github.com/Dicklesworthstone/mcp_agent_mail_rust)
  remain alternatives to evaluate before expanding this implementation.
