# Stellar Workspace, for the human who forgot

This is the operator handbook: how to set things up, talk to the agents, leave
for lunch, and recover afterward. Commands below run in your **external shell
on the workspace machine**, with that workspace's direnv environment active,
unless a step says otherwise.

## The 13-second version

```bash
cd ~/projects/YOUR-WORKSPACE
sw-agent start lead           # Codex runs HERE, in this terminal, in human mode
```

Choose another terminal/pane yourself, then run one worker there:

```bash
sw-agent start ada            # human-led; no automatic bead pickup
# OR, if you explicitly want assigned work picked up automatically:
sw-agent start ada --auto
```

You own the terminal layout. SW never creates, switches or destroys panes,
windows or tmux sessions. Keep the owning terminal open while the worker runs.
Quit its Codex UI to stop that launch and return to the shell; history remains.
New launches default to human mode, including after a previous auto session.

Usually return to the worker's existing terminal yourself. Optionally run
`sw-agent visit ada` in another terminal you choose: it connects there and pauses
new automatic pickup. Leaving that visit keeps the original worker running.
`sw-agent auto ada` explicitly returns it to its assigned queue.

Jump to [new workspace setup](#set-up-a-new-workspace), [team operation](#start-the-team-then-just-talk),
[shared IT](#shared-machine-setup-and-the-singleton-it-agent),
[maintenance](#broadcasts-and-gpu-maintenance), [review](#review-a-commit-or-branch),
[terminal keys](#ssh--windows-terminal--tmux), [updates](#update-or-repair-things),
or [troubleshooting](#when-something-looks-stuck).

## Find the right command

| I want to… | Command or action |
| --- | --- |
| See who's running and their mode/task | `sw-agent status` |
| Start the coordinator in this terminal | `sw-agent start lead` |
| Inspect Ada without opening a UI | `sw-agent status ada` |
| Discuss/steer Ada's current work | Return to her terminal, or `sw-agent visit ada` here |
| Give Ada a queued message | `sw-agent send ada 'Report progress at your next checkpoint.'` |
| Return Ada to assigned work | `sw-agent auto ada` |
| Suspend new pickup | `sw-agent pause ada` |
| Stop after the current Codex turn | `sw-agent stop ada --after-task` |
| Stop immediately | `sw-agent stop ada` |
| Read notices | `sw-agent motd` |
| Inspect all registered workspaces | `sw-agent status --all-workspaces` |
| Talk to the machine IT agent | `sw-agent --machine visit it` |
| Diagnose prerequisites | `sw-agent doctor` |
| Read backend diagnostics | `sw-agent logs ada` |
| Repair missing workspace files | `sw-init --repair` |
| Preview template upgrades | `sw-init --upgrade --dry-run` |
| Get instructions without this checkout | `sw-agent-readme --all` |

`--after-task` means **the current turn reaches idle**, not “the whole bead is
finished.” Pause does not interrupt a running tool or retract a queued message.
Immediate stop does not undo files already changed.

## What lives where

The canonical toolset checkout is `~/projects/stellar-workspace`. Install it into
each workspace; use a separate directory for the generated workspace itself.
The canonical checkout is a software project, not a workspace to initialize over.

| Location | What belongs there |
| --- | --- |
| Workspace root Git repository | Workspace configuration, docs, skills and metadata |
| `workspace.toml` | Workspace marker, repository catalog, sandbox settings and team roster |
| `sources/NAME/` | Independent source repositories, ignored by the workspace root |
| `.venv/` | This workspace's own direnv Python environment |
| `programs/NAME/`, `programs/bin/` | Local program installations; only `programs/bin` is on PATH by default |
| `build/`, `cache/` | Build outputs and reusable data |
| `.tmp/`, `scratch/` | Temporary files and disposable experiments/downloads |
| `worktrees/` | Explicit task checkouts |
| `agents/NAME/` | Agent instructions and its own build/cache/tmp/scratch/programs/logs/state |
| `.sw/managed.json` | Tracked template provenance; keep it with root metadata |
| `.sw/agents/NAME/` | Ignored controller state, mode, session UUID and receipts |
| `.beads/` | The workspace's single task tracker |
| `MOTD.md` | Current project announcements |
| `~/agent-shared/` | Shared machine notices, versioned assets and the IT workspace |

The root repo and each source repo have separate Git status, branches and commits.
A catalog entry does not clone or synchronize anything. No automatic scratch
cleanup occurs. Agent areas are cooperatively owned: permission from you or the
owning peer, including a scoped triage bead, permits working in another area.
They are not isolated from each other by filesystem access controls.

## Set up a new workspace

Prerequisites: Python 3.11+, Git, direnv, Linux/Bubblewrap with working user
namespaces and Codex. Managed interactive operation has been tested with
Codex 0.162.1 and beads-rust 0.7.6; treat those as qualified versions, not a claim
about whichever release is newest. Pi and omp managed adapters are future work;
Claude support has been removed.

Run before creating a venv or installing the package:

```bash
SW_TOOLS="$HOME/projects/stellar-workspace"
SW_NEW_WORKSPACE="$HOME/projects/my-workspace"   # choose your actual destination
python3 "$SW_TOOLS/sw-init.py" "$SW_NEW_WORKSPACE" --team
cd "$SW_NEW_WORKSPACE"
# Read .envrc, including any inherited parent settings, before trusting it.
direnv allow
python -m pip install "$SW_TOOLS"
sw-agent install-br --dry-run
sw-agent install-br
sw-agent init-beads
sw-agent doctor
```

Direnv creates and selects this workspace's `.venv`, even if a parent already has
one. Set `SW_PYTHON=/path/to/python3` before first activation to choose the base
interpreter. Run `direnv allow` yourself from the external shell. Bootstrap does
not grant trust, create Git repositories, clone sources, install packages, start
agents, or initialize beads on its own.

`--team` adds the roster, notices, role/name instructions, and coordination
skills. For an existing workspace, activate its venv, install/update this toolset,
then run `sw-init --team`. Team support is optional for sandbox/review use.

`install-br` installs a checksum-verified, pinned Linux release into
`programs/br/bin/br`; it refuses overwriting an existing binary. `init-beads`
refuses an existing tracker. Do not remove a tracker just to make setup succeed.
Inspect it and plan migration separately, preserving databases, journals and
exports. You can instead select a qualified existing br using `team.br`.

Initialize/maintain the root metadata Git repository deliberately. To add a
source repository, ask an agent to use `skills/add-repository/SKILL.md`, naming
the remote and intended branch. It clones into `sources/NAME/` and records:

```toml
[[repositories]]
name = "example"
path = "sources/example"
remote = "https://example.org/team/example.git"
branch = "main"
```

Keep it an independent repository, rather than a submodule or copied source tree.

## Keep the right Python and tools on PATH

From [machine setup](docs/machine-setup.md): login shells can replace the sandbox
PATH, hiding `sw-*` commands or selecting system Python. On the remote host, put
this at the **top level**, before any table headers in `~/.codex/config.toml`:

```toml
allow_login_shell = false
```

It makes Codex commands use non-login shells and rejects explicit login-shell
requests. Isolated profiles do not inherit host configuration. Set it in each
profile's own config too:

| Codex session | Config file |
| --- | --- |
| Host/shared-state Codex | `~/.codex/config.toml` |
| Standalone isolated workspace profile | `cache/agent-state/codex/config.toml` |
| Named worker | `agents/NAME/state/codex/config.toml` |

Create the selected profile directory if needed, and edit its config before
starting that session. Preserve existing settings. Copying your entire host
config into an isolated profile defeats the deliberate separation of host
settings and potentially embedded credentials.

In the external workspace shell, `command -v python` should select
`WORKSPACE/.venv/bin/python`. Inside the sandbox, the environment is rebuilt;
put necessary SDK settings in `[sandbox.env]` and configure explicit mounts.
Host environment exports alone do not configure the sandbox.

## Start the team, then just talk

```bash
# Choose one terminal per agent; each command stays in the foreground.
sw-agent start lead
# In a different terminal, if you want autonomous assigned-bead pickup:
sw-agent start ada --auto
```

For example:

> Investigate the GPU regression in sources/example. Create bounded beads for
> Ada and Grace, record the base commit and checks, and have Lin review the exact
> candidate commits. Keep integration and publication with me. Ask IT for any
> shared model or ROCm preparation.

Every agent begins in human mode unless you explicitly pass `--auto`.
The operator chooses where each process runs. The sandboxed lead assigns and coordinates
work; it does not launch nested supervisors. Agents ask
you when another worker is needed; you choose its terminal and launch it there.

The roster is `[team.agents.NAME]` in `workspace.toml`. The defaults are `lead`,
`ada`, `grace`, `lin`, and `it`; IT runs in the shared IT workspace, not separately
in each project. To add a name, edit the roster and run `sw-init --team` to create
its instructions. Supported roles: `lead`, `coder`, `reviewer`, `it`.

Quit the owning Codex UI when you want that launch to stop. Conversation history
survives. Closing an optional `visit` closes only that additional UI connection.
There is no background launch or automatic restart after disconnect/reboot.
You can manage your own terminal multiplexer; SW never operates it.

You can also request a stop from another shell:

```bash
sw-agent stop ada --after-task
sw-agent status
```

`--after-task` waits for the current turn to become idle. A new start resumes
the same conversation in human mode, even if the previous launch was auto. An
unfinished active bead forces `needs-human`: reconcile its work before enabling
pickup again. Do not use a start loop: the first foreground launch stays open.

## Beads without tab-hopping

You can delegate task bookkeeping to the lead or do it directly:

```bash
sw-agent beads create 'Investigate GPU regression' --assignee ada --json
sw-agent beads ready --assignee ada --json
sw-agent assign sw-EXAMPLE ada
sw-agent beads show sw-EXAMPLE --json
sw-agent beads comments add sw-EXAMPLE 'Please check this additional failure.'
```

Use real IDs returned by the tracker. `sw-agent beads` selects the canonical
workspace tracker even from a source checkout. Do not initialize another tracker
in an agent directory or worktree. Agents use their stable names as actors.

An auto worker wakes only for open, dependency-ready beads assigned to its exact
name. Unassigned backlog, in-progress work, and labels `motd`,
`sw:awaiting-review`, or `sw:needs-human` do not qualify. Local polling makes no
model calls while idle. A conditional claim guards against stale assignments.

The worker records changes, exact commits, checks and next actions in bead
comments. `working`, `waiting`, `review`, and `needs-human` checkpoints control
its local workflow; they **do not** close beads or update labels automatically.
A review handoff should leave suitable labels/status and a separate assigned
review task. Do not block that review task on the still-open implementation bead.
Source changes and review feedback remain in Git; beads track the work.

Root commits, integration, merges, pushes, direnv trust and host administration
stay with the human unless explicitly authorized. Agents can make task-branch
commits when the assigned workflow permits them.

## Shared machine setup and the singleton IT agent

Run once on the machine, from an initialized project workspace:

```bash
sw-agent init-shared --path ~/agent-shared --dry-run
sw-agent init-shared --path ~/agent-shared
cd ~/agent-shared/it
# Review this workspace's .envrc too.
direnv allow
python -m pip install "$HOME/projects/stellar-workspace"
sw-agent install-br
sw-agent init-beads
sw-agent --machine start it     # foreground here; human mode
```

The IT workspace has its own venv, tracker and conversation. Shared siblings are
`models/`, `rocm/`, `manifests/`, `staging/`, `control/`, and `MOTD.md`. Every
participating project must use the same `[team].shared_root` (default
`~/agent-shared`). Ordinary project initialization does not create this area.

From a configured project:

```bash
sw-agent --machine status
sw-agent --machine beads create 'Stage a versioned ROCm installation' --assignee it --json
sw-agent --machine visit it
sw-agent --machine auto it
```

`--machine` switches to the shared IT workspace/tracker. `--workspace PATH`
selects a project explicitly; avoid accidentally sending a machine task to the
project tracker. Cross-tracker relationships are explicit IDs/comments, not
cross-database bead dependencies.

Project agents read machine notices/control metadata. Grant additional shared
asset access explicitly in the relevant roster table, for example:

```toml
[team.agents.ada]
role = "coder"
shared_ro = ["models", "rocm"]
shared_rw = []
```

Restart the worker after mount/config changes. Shared paths are relative to
`shared_root`. A bead does not grant new mounts. IT gets writes to shared asset,
staging, manifest, notice and control areas; it has no implicit sudo/driver/
reboot/GPU-reset authority. Keep installations versioned and never replace an
asset directory being used by another job.

## Broadcasts and GPU maintenance

Edit `WORKSPACE/MOTD.md` for project announcements or `~/agent-shared/MOTD.md` for
machine-wide announcements. State the owner, affected resources, requested action
and when the notice clears. Changed notices are queued once to active agents,
including paused/human-mode agents; they do not interrupt a running tool.

```bash
sw-agent motd
sw-agent motd status --all-workspaces
sw-agent maintenance request --reason 'IT: drain GPU work for ROCm validation'
sw-agent maintenance status
# After checking acknowledgements AND actual process/device release, do approved work.
sw-agent maintenance release --reason 'IT: validation complete'
```

Publish the announcement separately from setting the flag. Have each agent read
and acknowledge the current hash with `sw-agent motd ack HASH` in its named
session. A receipt is not proof that a GPU is free. Inspect actual processes,
including unmanaged jobs, before disruptive machine work.

Maintenance pauses **all new automatic pickup**, including CPU tasks, across
configured workspaces. It neither kills existing jobs nor reserves GPUs. Manual
work and notice delivery continue. Release maintenance explicitly and update the
notice when done. IT may need a human-led session to work while pickup is paused.

## Run a one-off sandbox

```bash
sw-sandbox --dry-run
sw-sandbox --agent-profile codex -- codex
sw-sandbox --no-gpu --agent-profile codex -- codex
sw-sandbox --no-network -- python -m pytest
sw-sandbox --gpu --ro /opt/rocm -- COMMAND
sw-sandbox --agent-profile codex --gh-proxy -- gh pr list -R owner/repo
```

No command opens Bash. Workspace files/venv are writable; system files are
read-only; workspace `.tmp` appears as `/tmp`. Extra `--ro`/`--rw` mounts use real
paths; relative paths are workspace-relative. External symlink targets need
explicit mounts. There is no unsandboxed fallback when Bubblewrap is unavailable.

Network and GPU access default on. On machines without AMD devices, persist
`sw-init --set sandbox.gpu false` or use `--no-gpu`. Named agents inherit this
setting unless their roster entry overrides `gpu`. SDK mounts and environment
remain explicit. `--no-network` cannot be combined with the GitHub proxy.

**Credential distinction to remember:** plain `sw-sandbox -- codex` shares your
host `~/.codex`, including config, skills, history and any secrets embedded there.
`--agent-profile codex` instead uses local state and seeds only provider auth.
Named workers always use the isolated profile. Provider auth is intentionally
available to the selected client; GitHub and PyPI machine auth are excluded.

Keep credentials out of workspace files, notices and exposed data. The launcher
hides host Git/GitHub and publishing credentials, including relevant environment,
config, netrc and keyring state. It disables package credential discovery inside
the sandbox. Host Git identity is hidden too: configure `user.name`/`user.email`
locally in the source repository if needed.

The optional GitHub proxy authenticates read-only queries on the host. It denies
writes, raw API access and unsupported commands/options. A denial belongs to you;
agents must not bypass it. It guards accidental writes, with broader hardening
still future work.

## Review a commit or branch

```bash
sw-review -C sources/example open TOPIC BASE
sw-review -C sources/example open TOPIC BASE --merge-base --no-browser
sw-review -C sources/example comments TOPIC --unresolved
sw-review -C sources/example show TOPIC
sw-review -C sources/example open TOPIC BASE --static review.html
```

Replace `TOPIC` and `BASE` with actual refs/SHAs. Default comparison is the two
endpoints; `--merge-base` compares from their fork point. Uncommitted/index
changes are excluded. Click old/new line numbers to comment; use the UI to resolve
feedback and record verdicts. Static exports are read-only. Global `-C` and
`--author` options go before the subcommand.

Feedback lives in `refs/notes/sw-review` on the **exact reviewed commit**. It
stays local unless you deliberately synchronize notes; ordinary pushes need not
include them. A new commit or rebase does not inherit approval. Notes mutations
require Git author identity. The review tool has no beads coupling; reference
review commit IDs in bead handoffs.

Over SSH, choose a port and forward it from your local terminal:

```bash
# Remote workspace shell:
sw-review -C sources/example open TOPIC BASE --no-browser --port 8765
# Separate local terminal (replace YOUR_HOST):
ssh -N -L 8765:127.0.0.1:8765 YOUR_HOST
```

Open the URL printed by the review server in your local browser. Keep the server
and SSH tunnel running while reviewing. The server listens on remote loopback.

## SSH + Windows Terminal + tmux

These are the tested setup notes from [docs/machine-setup.md](docs/machine-setup.md).
They apply to ordinary SSH terminals too. Tmux is entirely optional and managed
by you; SW never sends terminal-navigation commands.

| Action | Keys |
| --- | --- |
| End the owning agent launch | Quit its Codex UI; the shell returns |
| Select text locally instead of sending mouse events to Codex/tmux | Hold Shift while dragging |
| Copy the selection to Windows | Ctrl+Shift+C |
| Paste into another session | Ctrl+Shift+V |
| Submit a Codex prompt | Enter |
| Insert a newline in the tested composer | Ctrl+J |

If Shift+Enter/Ctrl+Enter submit instead of inserting a newline, first verify
Ctrl+J works. In Windows Terminal, open **▼ → Settings → Open JSON file**. Merge
these entries into the existing top-level arrays, preserving other settings and
replacing any conflicting bindings:

```json
{
  "actions": [
    {
      "command": { "action": "sendInput", "input": "\n" },
      "id": "User.sendInput.DFCDAF06"
    }
  ],
  "keybindings": [
    { "id": "User.sendInput.DFCDAF06", "keys": "shift+enter" },
    { "id": "User.sendInput.DFCDAF06", "keys": "ctrl+enter" }
  ]
}
```

Save with Ctrl+S and test both shortcuts. They should insert a newline while
plain Enter still submits. The action and bindings must share the same ID;
Windows Terminal may rewrite the ID or normalize `"\u000a"` to `"\n"`. Both
encode the Ctrl+J line-feed byte. These bindings affect other applications in
Windows Terminal too. To undo them, remove the two bindings and the action if
nothing else references it. This JSON is a fragment to merge, not a replacement
for your whole settings file.

## Update or repair things

Activate each workspace in turn, including the shared IT workspace:

```bash
python -m pip install --force-reinstall "$HOME/projects/stellar-workspace"
sw-init --upgrade --dry-run
sw-init --upgrade
```

Reinstall updates that venv's installed package/resources. Upgrade separately
updates unchanged managed scaffolding. Local edits are preserved; conflicting
upgrades show diffs and make no changes. Reconcile them manually. Backups of
replaced files are under `.tmp/sw-init-backups/TIMESTAMP/`.

`sw-init --repair` restores missing scaffolding. If the workspace marker is
missing, supply the path explicitly: `sw-init /path/to/workspace --repair`.
Neither repair nor upgrade is permission to delete/recreate the venv or tracker.
Restart workers deliberately after updating runtime code/config; running
controllers are long-lived processes. Coordinate changes to the shared venv.

Edit repository tables, team settings and `[sandbox.env]` directly in
`workspace.toml`. `sw-init --set` handles supported name/sandbox boolean/list
settings; for example:

```bash
sw-init --set sandbox.gpu false
sw-init --set sandbox.ro '["/opt/rocm"]'
```

Mounts must exist. Avoid broad home/config mounts. Workspace discovery uses
`--workspace`, then `SW_WORKSPACE`, then the nearest `workspace.toml` above cwd;
check that selection before operating across projects.

## When something looks stuck

| Symptom | First checks and recovery |
| --- | --- |
| `sw-*` missing or wrong Python | Activate this workspace's direnv; verify `.venv/bin/python`; install here. For Codex shell commands, check `allow_login_shell = false` in the actual profile. |
| Worker never starts | Run `sw-agent doctor`; inspect `sw-agent logs NAME`, `agents/NAME/logs/controller.log`, and errors in its owning terminal. Check Bubblewrap, selected Codex/br, venv and tracker. |
| GPU device missing | Use `--no-gpu` for one-off commands or set `sandbox.gpu false` before starting workers. |
| Assigned task does not wake | Check worker running/mode, exact assignee, readiness/dependencies, status, exclusion labels, active bead and maintenance flag. After reconciling, `sw-agent auto NAME` retries pickup. |
| I left a visit and work stopped arriving | `visit` left human mode in place. Choose `sw-agent auto NAME` if you want automatic pickup again. |
| Worker says `needs-human` after restart | Inspect the in-progress bead and dirty files; give recovery instructions. Do not clear/reassign another worker's work blindly. |
| I quit the owning native UI | That launch stopped. Run `sw-agent start NAME` in the terminal you choose to resume its history. |
| Start says the worker is already running | Return to its original terminal or use `visit NAME` in this one. To move its owning terminal, stop that worker deliberately, then start here. |
| Templates conflict on upgrade | Read the proposed diff, preserve your local edits, reconcile manually, retry. |
| Sandbox GitHub command denied | Perform the needed write yourself in the authorized host workflow; do not ask the agent to find another route. |
| Review lost approval after a new commit | Read the old reviewed SHA explicitly. New code needs its own review; feedback is commit-scoped. |

### Moving off the old tmux setup

Existing processes keep the old behavior until stopped. In an external shell,
inspect `sw-agent status`, pause workers you want to park, then request
`sw-agent stop NAME --after-task` when appropriate. Check unfinished beads and
dirty files before restarting; stopping does not undo their changes. Reinstall
this checkout into the workspace venv, then launch individual workers in terminals
you choose. New code does not attach to or clean up old tmux sessions. Avoid
broad tmux kill commands that could affect unrelated work.

Custom workspace instructions may still contain the old startup loop/default-auto
advice. Reconcile it when `sw-init --upgrade --dry-run` reports local-edit conflicts.

After a machine restart, start the project workers and IT agent again explicitly.
Use `status`, `motd`, and the current beads to regain context before resuming.

## Where to look next

| Reference | Use it for |
| --- | --- |
| [README.md](README.md) | Authoritative project features, installation, sandbox and review behavior |
| [docs/multi-agent.md](docs/multi-agent.md) | Living team design, exact lifecycle/claim semantics and limitations |
| [docs/machine-setup.md](docs/machine-setup.md) | Remote-host and Windows Terminal setup details and upstream references |
| Workspace `AGENTS.md` and `skills/` | Local project rules and procedures; include your project-specific context here |
| `sw-agent-readme` | Installed concise operating guide |
| `sw-agent-readme init\|sandbox\|review\|config\|team\|machine` | Choose one topic; `--all` prints everything |
| `sw-agent --help`, `sw-sandbox --help`, `sw-review --help` | Exact CLI syntax |

Maintain this handbook when the operator workflow changes. Keep protocol/design
decisions in the living multi-agent doc and machine-specific findings in machine
setup; update the practical steps here with them.
