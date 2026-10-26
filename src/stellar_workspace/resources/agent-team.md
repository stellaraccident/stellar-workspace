# Persistent interactive team

Operator setup: `sw-init --team`, then `sw-agent install-br --dry-run`,
`sw-agent install-br`, `sw-agent init-beads`, and `sw-agent doctor`.
Requires Linux/Bubblewrap, br 0.7.6 and Codex native queue/remote App Server
(tested with 0.162.1). Existing trackers are preserved, never migrated implicitly.
The human chooses a terminal and runs `sw-agent start NAME`; it stays in the
foreground and opens the native Codex UI there. Every launch defaults to human
mode. Only explicit `start NAME --auto` or `auto NAME` enables assigned-bead
pickup. Never silently restore automation because the previous run used it.

SW does not manage terminal windows, panes or tmux sessions. The human chooses
which terminal runs each agent. Do not start agents on the human's behalf or
suggest a start loop: the first foreground launch stays open. Sandboxed agents
manage beads and scheduling modes; nested supervisors are unsupported.

`visit NAME` opens an additional native connection in the caller's current
terminal and sets human mode; leaving the visit leaves the owning start running.
Quitting the owning native UI stops its controller/backend and returns the shell.
History survives; another start resumes the same conversation in human mode.
Use status/logs for inspection. Keep the owning terminal alive to keep work alive.

Scope options work before or after subcommands: `sw-agent --workspace PATH --machine ...`.
Normal workspace discovery also uses SW_WORKSPACE / nearest workspace.toml.
Commands: start/visit/auto/pause/stop/status/logs/send, assign ID NAME,
claim ID [--name NAME], checkpoint --state working|waiting|review|needs-human
[--bead ID], beads ARGS..., motd [show|status|ack REVISION], maintenance
status|request|release [--reason TEXT]. In workers, SW_AGENT supplies identity.

Use `sw-agent beads` for the canonical .beads directory and actor, including from
source checkouts. Task selection uses assigned ready open beads, excludes motd,
sw:awaiting-review and sw:needs-human labels, and never picks unassigned backlog.
An automatic wake is a hint: verify actual mode, readiness and ownership first.
A conditional claim prevents stale selection from starting work. An existing
in-progress task requires human reconciliation after crashes, not automatic
reclaim. Use comments to add handoff evidence; do not replace issue history.

Stay in your own directory/working checkout unless the human or owning peer
permits a scoped visit, including via an assigned triage bead. Read your role
and local AGENTS.md, project docs and both MOTDs. Preserve existing/dirty work.
Each agent owns build/cache/tmp/state and conversation history; the workspace
venv is shared for tooling, so serialize modifications to it.
GPU access inherits sandbox.gpu (on by default). Set gpu on an individual
team.agents.NAME table only to override the workspace setting.

Before new tasks/GPU work, read `sw-agent motd`. A changed MOTD is queued to the
same Codex session, not guaranteed to interrupt a running tool. Acknowledge its
current hash with `sw-agent motd ack HASH`; acknowledgement does not prove GPU
release. Human input takes priority; never resume automatic pickup after a human
interrupt without explicit auto. No model-powered idle polling is needed.

Only task-branch commits are within normal coding autonomy when the task permits.
No unsolicited root commits, merges, pushes, direnv trust or host administration.
Provider auth is selected explicitly; host configs, shell snapshots and GitHub/
PyPI tokens remain excluded. The outer sandbox is mandatory for managed backends.
The controller never executes model-supplied host commands.
