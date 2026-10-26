---
name: team-operation
description: Coordinate this workspace's named interactive Codex workers through assigned beads and MOTD.
---

Read `sw-agent-readme team`. The human starts foreground workers in terminals
they choose and talks to the lead there. SW never manages windows/panes/tmux.
Default mode is human; --auto or auto NAME requires explicit human opt-in. Make bounded
beads with source/base, acceptance and checks; assign them to stable names. Auto
workers receive a queue hint and claim conditionally. Use status for mode/task,
visit for the same native transcript/conversation, and auto to return scheduling.
Never replace native interactive workers with exec/log-tail batch jobs.

Treat agent areas as cooperatively owned. An explicit human/peer permission or
assigned triage bead may authorize scoped work in another area; record it and
hand back results. Never reset another dirty checkout. Keep root commits,
integration and publication with the human unless explicitly requested. Use
exact candidate commits for review and bead comments for handoffs. Notices are
MOTD, not another queue. Do not duplicate trackers inside worker/source checkouts.
