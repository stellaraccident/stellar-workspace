# Linux sandbox

`sw-sandbox [--workspace PATH] [OPTIONS] -- COMMAND ...`; no command opens Bash.
`--dry-run` prints effective mounts, environment and capabilities as JSON without
starting services or children. A local `.venv` and Linux Bubblewrap are required.
Missing tools never cause an unsandboxed fallback.

Required system directories are read-only, home/proc/dev are synthetic, and the
workspace is writable. Workspace `.tmp` is also `/tmp` (TMPDIR/TMP/TEMP). The local
venv is writable; external Python base paths are read-only. Host environment is
cleared; `.envrc` is not executed. Put explicit extra values in sandbox.env.

- `--no-network` isolates networking; it cannot be combined with the GitHub proxy.
- `--gpu` exposes AMD /dev/kfd, /dev/dri and read-only /sys. SDK mounts/env remain
  explicit. Missing requested devices are errors.
- `--ro PATH` / `--rw PATH` add mounts; relative paths use the workspace root.
  External symlink targets need explicit mounts. Protected overlays, credential
  directories and mounts overlapping host GitHub/PyPI/Git credential paths are denied.
  Mount specific external CLI/runtime paths, not broad home/config directories.
- `--agent-profile codex|claude` seeds only ~/.codex/auth.json or
  ~/.claude/.credentials.json into workspace cache/agent-state/PROFILE, then
  persists local config/sessions there. Seeds are mode 0600, copied only if
  missing, and do not update the host originals. Provider auth is intentionally
  exposed to the selected agent. Host config, shell snapshots, old sessions and
  ~/.claude.json are excluded because they may embed GitHub tokens. CLIs are
  not automatically installed or mounted.
- Host ~/.gitconfig, Git credentials, netrc, GitHub configuration (including a
  custom GH_CONFIG_DIR) and keyring directories remain hidden. Use repository
  local Git identity settings if needed. Host token environment variables
  never reach the sandbox, including its Bubblewrap supervisor or /proc.
- PyPI auth is hidden too: ~/.pypirc, pip/uv/Poetry config and credential stores,
  custom PIP_CONFIG_FILE, site .venv/pip.conf, netrc and keyrings. TWINE_*, PIP_*,
  UV_*, PYPI_* and other packaging auth environment overrides are denied. Pip
  config loading and pip/uv/Python keyring lookup are disabled inside the
  sandbox. Credential files are masked in the sandbox without changing originals.
- `--gh-proxy` allows supported read commands over an owned host socket. Host
  credentials stay on the host; known token values are redacted from responses.
  Configured environment aliases containing known credentials are rejected too.
  GitHub writes and attempts to bypass the proxy are off-limits. Leave denied
  actions to the human. Raw API, unknown options, downloads and mutations are
  denied. This proxy guards accidental writes; comprehensive proxy hardening
  remains future work. Do not put credentials in writable workspace/data mounts.

CLI boolean options override configuration (including --no-gpu/--no-gh-proxy).
Mount flags append; --agent-profile replaces profiles. Child status/signals
propagate. Owned proxy/socket/runtime resources are cleaned up after execution.
