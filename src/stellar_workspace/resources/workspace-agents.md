# __NAME__: agent instructions

This root repository holds workspace metadata; independent code repositories
live in `sources/` and are cataloged in `workspace.toml`. Inspect Git status in
the intended repository before editing. Preserve existing work. Do not commit,
push, or change root branches unless requested.

Direnv selects this workspace's `.venv`, even when a parent has a venv. Run
`direnv allow` only from the human's external shell. After activation install
with `python -m pip install /path/to/stellar-workspace`; update with
`python -m pip install --force-reinstall /path/to/stellar-workspace`.
Before installation, run `python3 /path/to/stellar-workspace/sw-init.py PATH`.
Once installed, run `sw-agent-readme` and use `sw-init --upgrade` or `--repair`
for managed scaffolding. Read this file's local additions and project docs too.

Keep build outputs in `build/`, caches in `cache/`, local programs in
`programs/NAME/` (or `programs/bin`), temporary files in `.tmp/`, and throwaway
experiments/downloads in `scratch/`. These directories are untracked.

GitHub access through the sandbox proxy is read-only. GitHub writes and attempts
to bypass the proxy are off-limits. A denied action must be left to the human.
The proxy guards accidental writes; do not treat it as adversarial isolation.
Host GitHub and PyPI credentials must stay hidden. Do not place credentials in
workspace files or expose them through mounts, environment overrides or helpers.

Read the relevant workspace skill when needed:

- [Add a repository](skills/add-repository/SKILL.md)
- [Workspace environment](skills/workspace-environment/SKILL.md)
- [Sandbox workflow](skills/sandbox-workflow/SKILL.md)
- [Local review](skills/local-review/SKILL.md)

Add project-specific context below. Local edits are preserved by maintenance.
