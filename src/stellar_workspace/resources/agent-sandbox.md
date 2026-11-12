# Linux sandbox

`sw-sandbox [--workspace PATH] [OPTIONS] -- COMMAND ...`; no command opens Bash.
`--dry-run` prints effective mounts, environment and capabilities as JSON without
starting services or children. A local `.venv` and Linux Bubblewrap are required.
Missing tools never cause an unsandboxed fallback.

Required system directories are read-only, home/proc/dev are synthetic, and the
workspace is writable. Workspace `.tmp` is also `/tmp` (TMPDIR/TMP/TEMP). The local
venv is writable; external Python base paths are read-only. Host environment is
cleared; `.envrc` is not executed. Put explicit extra values in sandbox.env.
Existing ~/.local/bin, ~/.local/lib/node_modules and
~/.codex/packages directories are read-only, including with agent profiles.
~/.local/bin is on PATH after workspace tools and before system tools. Other
local data stays hidden. Symlinked installation directories need explicit mounts.

By default existing ~/.codex is shared read-write for host login, config, skills,
credential refreshes and sessions; its packages/ tree stays read-only. This is
intentional host state sharing, including any secrets embedded in config or
shell snapshots. Use --agent-profile codex for isolated workspace-local state.

- `--no-network` isolates networking; it cannot be combined with the GitHub proxy.
- GPU access defaults on, exposing AMD /dev/kfd, /dev/dri and read-only /sys.
  Use `--no-gpu` to disable it. SDK mounts/env remain explicit. Missing requested
  devices are errors.
- `--ro PATH` / `--rw PATH` add mounts; relative paths use the workspace root.
  External symlink targets need explicit mounts. Protected overlays, credential
  directories and mounts overlapping host GitHub/PyPI/Git credential paths are denied.
  Mount specific external CLI/runtime paths, not broad home/config directories.
- `--dev PATH` adds a Bubblewrap `--dev-bind` mount (repeatable). Explicit
  children of `/dev`, such as `/dev/fuse`, are allowed; mounting all of `/dev`
  is denied. Other protected-path and mount-conflict checks still apply.
- `--cap-add CAP` retains a capability in the sandbox user namespace (repeatable).
  FUSE mounting can require `--dev /dev/fuse --cap-add CAP_SYS_ADMIN`.
  This grants mount administration inside the sandbox namespace; host restrictions
  still apply. No extra capabilities are retained by default.
- `--fuse` implies `--dev /dev/fuse --cap-add CAP_SYS_ADMIN` without adding
  duplicate implied entries. The host must provide `/dev/fuse` and permit mounts.
  Commands run through util-linux `unshare --mount` so the mount namespace is
  owned by the final sandbox user namespace. This requires `unshare` on the host.
- `--agent-profile codex` replaces the default host state mount and seeds only
  ~/.codex/auth.json into workspace cache/agent-state/codex, then
  persists local config/sessions there. Seeds are mode 0600, copied only if
  missing, and do not update the host originals. Provider auth is intentionally
  exposed to the selected agent. Host config, shell snapshots and old sessions
  are excluded in this mode because they may embed GitHub tokens. CLIs must
  already be installed in a default tool directory or explicitly mounted.
- Host ~/.gitconfig, Git credentials, netrc, GitHub configuration (including a
  custom GH_CONFIG_DIR) and keyring directories remain hidden. Use repository
  local Git identity settings if needed. Host token environment variables
  never reach the sandbox, including its Bubblewrap supervisor or /proc.
- PyPI auth is hidden too: ~/.pypirc, pip/uv/Poetry config and credential stores,
  custom PIP_CONFIG_FILE, site .venv/pip.conf, netrc and keyrings. TWINE_*, PIP_*,
  UV_*, PYPI_* and other packaging auth environment overrides are denied. Pip
  config loading and pip/uv/Python keyring lookup are disabled inside the
  sandbox. Credential files are masked in the sandbox without changing originals.
- `--gh-proxy` allows supported read commands over an owned host socket. GitHub
  credential files stay hidden; known token values are redacted from responses.
  Default Codex sharing can expose tokens embedded in ~/.codex files.
  Configured environment aliases containing known credentials are rejected too.
  GitHub writes and attempts to bypass the proxy are off-limits. Leave denied
  actions to the human. Raw API, unknown options, downloads and mutations are
  denied. This proxy guards accidental writes; comprehensive proxy hardening
  remains future work. Do not put credentials in writable workspace/data mounts.

CLI boolean options override configuration (including --no-gpu/--no-gh-proxy).
Mount flags append; --agent-profile replaces profiles. Child status/signals
propagate. Owned proxy/socket/runtime resources are cleaned up after execution.
