# Stellar Workspace: agent operating guide

Read local `AGENTS.md` and project context first. The root tracks metadata;
code belongs in independent `sources/` checkouts cataloged in `workspace.toml`.
Inspect status in the intended repository; preserve existing changes. Do not
commit, push, or change root branches without a request.

Each workspace has a direnv-managed `.venv`. Bootstrap before installation with
`python3 /path/to/stellar-workspace/sw-init.py PATH`. The human reviews `.envrc`
and runs `direnv allow` from an external shell. After activation, install using
`python -m pip install /path/to/stellar-workspace`; update using
`python -m pip install --force-reinstall /path/to/stellar-workspace`.

Use `sw-init --upgrade --dry-run` to preview template updates, `--repair` to
restore missing scaffolding, and `--set KEY VALUE` for supported config fields.
Local edits are preserved; resolve reported conflicts manually. Read relevant
starter skills under `skills/`, indexed in generated `AGENTS.md`.

Keep builds in `build/`, reusable data in `cache/`, programs in `programs/`,
temporary files in `.tmp/`, and throwaway work in `scratch/`. These are untracked.
`programs/bin` is on PATH. Do not install tooling into source repositories.

Use `sw-sandbox --dry-run` to inspect capabilities, then `sw-sandbox -- COMMAND`.
Linux/Bubblewrap is required. Network and GPU access default on; use `--no-gpu` without AMD devices. Isolated
agent state and GitHub proxy access are opt-in. Agent profiles seed provider auth into workspace-local
state without sharing host config or shell snapshots. Host GitHub/PyPI credentials
stay hidden, including publishing environment variables and package auth files. GitHub writes and
attempts to bypass the read-only proxy are off-limits; leave denials to the human.
The proxy guards accidents, not hostile clients.

Use `sw-review -C REPO open TOPIC BASE` for browser review. Agent feedback is
JSON via `comments REV --unresolved`, `add-comment`, `resolve`, `unresolve`,
`verdict`, and `show`. Notes at `refs/notes/sw-review` belong to a commit, do not
follow new commits/rebases, and are local unless explicitly synchronized.

Optional named teams use `sw-init --team`, then explicit br installation/tracker
setup. `sw-agent start NAME` creates a persistent sandboxed Codex session;
`visit NAME` opens its native UI and suspends automatic pickup until `auto NAME`.
Use canonical `sw-agent beads`, conditional `claim`, and recorded checkpoints.
Read workspace/shared MOTDs, respect peer areas, and use machine IT for shared
models/ROCm work when asked. See `sw-agent-readme team` and `machine`.

Details: `sw-agent-readme init|sandbox|review|config|team|machine`; `--all` prints every topic.
All commands support `--help`. Installed guidance needs no source checkout.
