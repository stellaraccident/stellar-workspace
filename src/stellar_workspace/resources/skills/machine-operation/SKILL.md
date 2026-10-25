---
name: machine-operation
description: Request or perform assigned shared model, ROCm and machine coordination work through the singleton IT agent.
---

Read `sw-agent-readme machine`. Use the explicit shared IT workspace/queue;
ordinary project tasks do not grant host administration or new mounts. Stage and
validate assets, then publish versioned directories/manifests. Preserve versions
used by active jobs. Serialize conflicting asset changes with resource-local locks.

For maintenance, publish a machine MOTD and request the shared pause flag. Collect
acknowledgements and verify actual GPU process release, including unmanaged jobs.
A notice, heartbeat or empty task queue does not establish safe reset. Prepare
concrete human actions for sudo/driver/reboot/reset operations. Release the pause
and announce resume explicitly. Keep GitHub/PyPI credentials outside all agent
sandboxes and shared assets; never reintroduce a host container socket.
