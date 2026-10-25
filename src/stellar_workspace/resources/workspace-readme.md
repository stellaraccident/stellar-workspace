# __NAME__

This workspace keeps independent Git checkouts in `sources/` and root metadata
in `workspace.toml`, `docs/`, `skills/`, and `tools/`. Register repository name,
relative path, remote and intended branch in `[[repositories]]` configuration.
The catalog does not clone or update checkouts automatically.

Direnv creates/activates a dedicated `.venv`. From your external shell:

```bash
direnv allow
python -m pip install '__SOURCE__'
# After toolset source changes:
python -m pip install --force-reinstall '__SOURCE__'
sw-agent-readme
```

Use `SW_PYTHON=/path/to/python3` before first activation to select a base Python
3.11+ interpreter. Parent `.envrc` settings are loaded before this workspace
selects its own venv. Review both files before trusting the configuration.

`build/`, `cache/`, `programs/`, `.tmp/`, `scratch/`, `.venv/`, `.direnv/` and
`worktrees/` are local/untracked. Put program installations in `programs/NAME/`
and small executables in `programs/bin`; only `programs/bin` is added by default.
`TMPDIR`, `TMP` and `TEMP` point to `.tmp/`. No automatic cleanup is performed.

Use `sw-init --dry-run`, `sw-init --upgrade --dry-run`, `sw-init --repair`, or
`sw-init --set sandbox.gpu false`. Maintenance preserves local edits and reports
conflicts; backups of replaced files live in `.tmp/sw-init-backups/`.

See `AGENTS.md` and its skill index. Add project setup and active documentation
pointers here.
