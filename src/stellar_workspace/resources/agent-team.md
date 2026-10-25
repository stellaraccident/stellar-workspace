# Persistent interactive team

Operator setup: `sw-init --team`, then `sw-agent install-br --dry-run`,
`sw-agent install-br`, `sw-agent init-beads`, and `sw-agent doctor`.
Requires Linux/Bubblewrap, tmux, br 0.7.6 and Codex native queue/remote App Server
(tested with 0.162.1). Existing trackers are preserved, never migrated implicitly.
The operator starts workers once from the external shell; sandboxed agents manage
beads and scheduling modes, and do not launch nested supervisors.

The operator starts a normal Codex lead with `sw-agent start lead`, then visits
it with `sw-agent visit lead`. Named workers have persistent conversations and
native Codex terminal UIs. They are not per-bead batch jobs. `visit NAME` sets
human mode and opens the same UI; `auto NAME` returns scheduling to assigned work.
`watch NAME` attaches read-only without changing mode. Detach with tmux's normal
Ctrl-b d. Do not restart/replace a conversation to send it another assignment.

Scope options work before or after subcommands: `sw-agent --workspace PATH --machine ...`.
Normal workspace discovery also uses SW_WORKSPACE / nearest workspace.toml.
Commands: start/visit/watch/auto/pause/stop/status/logs/send, assign ID NAME,
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
