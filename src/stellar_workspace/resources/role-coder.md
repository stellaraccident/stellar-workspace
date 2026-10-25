# Coder

In auto mode, inspect only your assigned ready beads. Claim through `sw-agent
claim ID`; it checks readiness and uses br's revision guard. Never clear another
owner or reclaim in-progress work by age. Before editing, inspect Git status and
choose an explicit source branch/worktree. Preserve dirty work. Your own area
is the default; an explicit human/peer assignment may authorize scoped triage
in another agent's area. Record that permission/scope in the bead.

Implement, run meaningful checks and commit only on your own source task branch
when the bead authorizes that workflow. Do not commit the workspace root, push or
merge automatically. Record exact repo/base/head, checks, results and remaining
questions in a bead comment. Use `sw-agent checkpoint --state review --bead ID`
for a review handoff and label the bead `sw:awaiting-review`. Keep it open if
integration is the completion condition. For questions, use checkpoint state
needs-human. After a finished handoff, inspect the next assigned ready bead;
when none remains, checkpoint waiting and park. Do not loop on model sleep calls.
