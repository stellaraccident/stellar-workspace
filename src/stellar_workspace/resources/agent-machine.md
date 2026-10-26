# Shared machine / IT

`sw-agent init-shared [--path ~/agent-shared] [--dry-run]` explicitly creates the
machine area and its IT workspace; ordinary project init never creates it.
Activate/install that workspace's own direnv venv, then install/initialize br
there. `sw-agent --machine start it` runs IT in the chosen foreground terminal,
in human mode unless --auto is explicitly selected. It targets that workspace from projects
configured with the same team.shared_root. It is not a new IT agent per project.

Shared layout: MOTD.md, models/, rocm/, manifests/, staging/, control/, it/.
Worker roles read the machine MOTD and control metadata. Additional shared assets
are workspace-relative-to-shared-root entries in team.agents.NAME.shared_ro/rw;
these are configured mount grants, not permissions a bead can add. Keep shared
assets versioned and pin task runs to exact versions; do not replace directories
under active jobs. Never put credentials in this shared asset tree.

IT publishes machine notices. Workspace leads publish local MOTD. Assign work
using the corresponding canonical tracker; link project and machine beads by
explicit IDs/comments rather than assuming a cross-database dependency engine.
Use `sw-agent --machine beads ...` and `--machine assign ID it` from a project.

`maintenance request --reason TEXT` sets the cooperative global pause flag;
release also requires a reason. This stops new automatic pickup, including CPU
tasks in the deliberately simple MVP. Human-led CPU work remains available.
It does not kill jobs, reserve GPUs or enforce an OS scheduler. IT must verify
acknowledgements AND actual process/device release, including unmanaged users,
before any approved disruptive operation. Unknown or unresponsive is not safe.
No implicit sudo/reboot/driver replacement/reset, no Podman host bridge, and no
GitHub/PyPI credential access is granted to IT.
