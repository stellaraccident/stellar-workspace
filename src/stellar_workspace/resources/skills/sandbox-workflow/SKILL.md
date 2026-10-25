---
name: sandbox-workflow
description: Run commands in the Linux workspace sandbox and select explicit mounts or host capabilities.
---

Read `sw-agent-readme sandbox` and inspect `sw-sandbox --dry-run` before relying
on filesystem or environment assumptions. Run `sw-sandbox -- COMMAND ...`; no
command opens Bash. Workspace files and local venv are writable, system paths
read-only. External symlink targets require explicit `--ro`/`--rw` mounts.

Network is enabled unless `--no-network` is selected. GPU (`--gpu`), persisted
agent state (`--agent-profile codex` or `claude`) and GitHub proxy (`--gh-proxy`)
are opt-in. Agent profiles seed provider auth into workspace-local state; host
config and shell snapshots remain hidden. Host GitHub/PyPI credentials, publishing
variables and package auth stores must stay outside the sandbox. Do not add them
to workspace files, mount lists or environment overrides.
Host GitHub bridging is incompatible with `--no-network`.

GitHub writes and attempts to bypass the proxy are off-limits. Use only
supported read commands; leave denied actions to the human. The initial proxy
is a guard against accidental writes, not adversarial isolation. Do not expose
host credentials or invoke alternate clients to work around a denial.
