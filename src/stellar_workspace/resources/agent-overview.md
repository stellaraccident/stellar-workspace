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
Linux/Bubblewrap is required. Network defaults on; GPU, agent state and GitHub
proxy access are opt-in. Agent profiles seed provider auth into workspace-local
state without sharing host config or shell snapshots. Host GitHub/PyPI credentials
stay hidden, including publishing environment variables and package auth files. GitHub writes and
attempts to bypass the read-only proxy are off-limits; leave denials to the human.
The proxy guards accidents, not hostile clients.

Use `sw-review -C REPO open TOPIC BASE` for browser review. Agent feedback is
JSON via `comments REV --unresolved`, `add-comment`, `resolve`, `unresolve`,
`verdict`, and `show`. Notes at `refs/notes/sw-review` belong to a commit, do not
follow new commits/rebases, and are local unless explicitly synchronized.

Details: `sw-agent-readme init|sandbox|review|config`; `--all` prints every topic.
All commands support `--help`. Installed guidance needs no source checkout.
