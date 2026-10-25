# Initialization and maintenance

Before installation: `python3 /path/to/stellar-workspace/sw-init.py PATH`.
Requires base Python 3.11+, no third-party modules. Afterwards, use `sw-init`.
Both invoke the same lifecycle implementation. Run with `--dry-run` to preview.

- `sw-init [PATH] [--name NAME]`: create missing skeleton and starter skills.
- `sw-init [PATH] --upgrade`: update unchanged managed templates.
- `sw-init [PATH] --repair`: restore missing scaffolding.
- `sw-init [PATH] --set sandbox.gpu true`: change supported configuration.

Maintenance without PATH discovers the workspace from SW_WORKSPACE or the
nearest workspace.toml. Creation defaults to the current directory. Keep
`.sw/managed.json` tracked: it records template hashes, tool version, and
canonical source path. Never copy provenance onto unrelated custom files.

Customized/unmanaged files are preserved. Upgrade conflicts show a diff and
make no changes. Reconcile edits manually before retrying. Existing matching
unmanaged files are not adopted. Backups of replaced files are under
`.tmp/sw-init-backups/TIMESTAMP/`; partial I/O failures report recovery location.
`--repair PATH` can restore a missing marker using provenance. Unsupported future
schema versions fail; schema 1 is the initial supported format.

Direnv loads parent settings, creates/activates this workspace's own `.venv`,
and exports local temporary paths. It uses a base interpreter from SW_PYTHON or
python3, even when started in another venv. Initializer never executes `.envrc`,
installs packages, grants direnv trust, creates Git repositories, or clones the
repository catalog. The human's external shell runs `direnv allow`; then use
its selected python to install the canonical source checkout.

Starter skills cover repository additions, environment setup, sandbox use and
local review. Upgrade/repair maintains their templates with the same local-edit
protections. Repository additions are user-requested actions, not background
synchronization. Source checkout branches/remotes remain explicit.
