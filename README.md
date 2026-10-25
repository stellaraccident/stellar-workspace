# Stellar Workspace

Installable tools for independent development workspaces: bootstrap and maintain
workspace scaffolding, run Linux agent sessions in Bubblewrap, and review Git
changes locally with feedback in Git notes. Agents get the full operating guide
from the installed package via `sw-agent-readme`.

For everyday setup, commands, terminal keys and recovery, start with
[HUMANS.md](HUMANS.md).

Requires Python 3.11+. Git, direnv, Bubblewrap and optional host CLIs are external
programs. Python runtime dependencies are Pygments and websocket-client. No PyPI publication is
required; install directly from this checkout.

## Bootstrap and install

Start from a base Python, before creating a venv or installing anything:

```bash
python3 /path/to/stellar-workspace/sw-init.py /path/to/new-workspace
cd /path/to/new-workspace
direnv allow
python -m pip install /path/to/stellar-workspace
sw-agent-readme
```

Review the generated `.envrc` before `direnv allow`, and run that trust action
from your external shell. It loads parent direnv settings, then creates and
activates the workspace's own `.venv`. An inherited venv never substitutes for
it. Set `SW_PYTHON=/path/to/python3` before first activation to select a base
interpreter. Initializer does not execute `.envrc`, create the venv, install
packages, initialize Git, clone sources, or grant direnv trust.

The source `sw-init.py` prepends its adjacent `src/` to Python's import path and
uses the same dependency-free initializer as the installed command. It works
from any directory without site packages or PYTHONPATH.

After changing this toolset, update each workspace's selected environment:

```bash
python -m pip install --force-reinstall /path/to/stellar-workspace
sw-init --upgrade --dry-run
sw-init --upgrade
```

Installation is non-editable by default and bundles templates, skills, UI and
agent instructions. Reinstallation updates only the selected environment; it
never rewrites workspace files automatically. Use editable installs only when
working on this toolset itself.

## Workspace layout

| Path | Purpose |
| --- | --- |
| `workspace.toml` | Tracked configuration, workspace marker, repository catalog |
| `AGENTS.md`, `README.md` | Generated basic setup and local project context |
| `.envrc`, `.gitignore` | direnv setup and local-output exclusions |
| `.sw/managed.json` | Tracked template provenance, version, canonical source path |
| `sources/` | Independent Git repositories, ignored by the workspace root |
| `docs/`, `skills/`, `tools/` | Tracked project documentation, skills and extensions |
| `.venv/` | Dedicated direnv-managed Python environment |
| `build/`, `cache/` | Untracked builds and reusable data |
| `programs/` | Untracked local program installations; `programs/bin` on PATH |
| `.tmp/`, `scratch/` | Untracked temporary and disposable experiments/downloads |
| `worktrees/`, `.direnv/` | Untracked worktrees and direnv state |

Root repositories hold metadata; code changes belong in the appropriate source
checkout. Keep branches/remotes explicit and preserve existing work. The toolset
never automatically deletes scratch data, commits, pushes or changes branches.

## Workspace lifecycle

```bash
sw-init [PATH] [--name NAME] [--dry-run]
sw-init [PATH] --upgrade [--dry-run]
sw-init [PATH] --repair [--dry-run]
sw-init [PATH] --set sandbox.gpu false
sw-init [PATH] --set sandbox.ro '["/opt/sdk"]'
```

Creation defaults to cwd. Maintenance without PATH uses workspace discovery.
`--upgrade` refreshes unedited managed templates, `--repair` restores missing
scaffolding, and repeatable `--set KEY VALUE` modifies supported configuration
fields without discarding unrelated settings/comments. Complex representations
are rejected rather than rewritten lossily. Current schema is 1; unsupported
schema versions fail clearly.

Managed provenance distinguishes generated files from local edits. Customized
or unmanaged files are preserved; conflicting upgrades print proposed diffs and
make no changes. Reconcile those manually. Existing identical unmanaged files
are not automatically adopted. Replaced files are backed up under
`.tmp/sw-init-backups/TIMESTAMP/`. Writes are atomic per file; an I/O failure
can leave a partial plan and reports the backup location. Restore from backups
or resolve the error and rerun repair. Managed symlink escapes are rejected.

Both entry points create/maintain four starter skills under `skills/NAME/SKILL.md`:
`add-repository`, `workspace-environment`, `sandbox-workflow`, and `local-review`.
The generated `AGENTS.md` indexes them and includes enough setup instructions
to work before installation. Skill maintenance preserves local edits too.

The repository catalog records intended checkouts, without cloning/updating:

```toml
[[repositories]]
name = "example"
path = "sources/example"
remote = "https://example.org/team/example.git"
branch = "main"
```

Use the `add-repository` skill for user-requested additions. Checkouts remain
independent repositories, not submodules or vendored source.

## Linux sandbox

```bash
sw-sandbox --dry-run
sw-sandbox -- bash
sw-sandbox --no-network -- python -m pytest
sw-sandbox --gpu --ro /opt/rocm -- COMMAND
sw-sandbox --agent-profile codex -- codex
sw-sandbox --gh-proxy -- gh pr list -R owner/repo
```

With no command, open interactive Bash with a sandbox prompt. Child status and
signals propagate. Requires Linux/Bubblewrap and a working local `.venv`; there
is no unsandboxed fallback. Root discovery uses `--workspace`, then
`SW_WORKSPACE`, then the nearest `workspace.toml` above cwd. An explicit invalid
root is an error. Working directory is retained when inside the workspace.

The effective plan lists mounts, environment and enabled capabilities as JSON.
Dry-run starts no proxies, children or services. Required system paths are
read-only; home is synthetic, workspace writable, and workspace `.tmp` also
mounted at `/tmp`. TMPDIR/TMP/TEMP inside the sandbox are `/tmp`. The local venv
is used even if another VIRTUAL_ENV is inherited; external base interpreter
paths are exposed read-only. Environment is rebuilt from an allowlist; `.envrc`
is not executed by the launcher.

Existing `~/.local/bin`, `~/.local/lib/node_modules`
and `~/.codex/packages` directories are exposed read-only. `~/.local/bin` is on
PATH after workspace tools and before system tools, so local Codex installations
work out of the box. Other local data stays hidden. Symlinked installation
directories and other external symlink targets still need explicit mounts.

By default, existing `~/.codex` is shared read-write, matching the original
workspace launcher. `sw-sandbox -- codex` uses your host login, configuration,
skills and session history, and persists credential refreshes and runtime state
on the host. The `packages/` installation tree remains read-only. This also
exposes any other secrets embedded in Codex config or shell snapshots; default
mode does not isolate host Codex state.

Network and GPU access default on. Workspace-local Codex state and the GitHub
proxy are opt-in. Use `--no-gpu` on hosts without AMD GPU devices. `--no-network` cannot be combined with host bridges. AMD GPU access
requires `/dev/kfd` and `/dev/dri`, and exposes read-only `/sys`. SDK environment
and mounts remain explicit. Named agents inherit `sandbox.gpu` unless their
`team.agents.NAME.gpu` overrides it. Existing explicit `gpu = false` settings
still disable access; use `sw-init --set sandbox.gpu true` to enable it in an
older workspace and remove unwanted per-agent overrides.
`--ro`/`--rw` append mounts at their real paths;
relative paths use the workspace root. External workspace symlink targets are
not mounted automatically. Protected overlays and SSH/GPG/AWS credential mounts
are rejected. The optional `--agent-profile codex` replaces shared host state
with workspace-local state and seeds only `~/.codex/auth.json` into
`cache/agent-state/codex/`, with mode 0600,
then persist local sessions/config there. They do not share host configuration,
shell snapshots, or existing sessions. CLIs must already be installed in a default
tool directory or made available with an explicit mount.
Provider auth is intentionally available in both modes.
Host Git config, Git credentials, GitHub CLI config (including GH_CONFIG_DIR),
netrc and keyring directories stay hidden; credential mount overlaps are denied.
Configure Git author identity locally in a source repository when needed.

GitHub and PyPI token environment variables are never inherited by the sandbox or its
Bubblewrap supervisor. Known token values are rejected in configured environment
aliases and redacted from proxy responses. The real-sandbox tests verify this
boundary with fake host tokens, credential files, `/proc` environment reads and
agent config/shell snapshots in isolated profile mode, while a proxied read
authenticates on the host. Default mode intentionally exposes secrets stored
under `~/.codex`.
PyPI protections also mask `.pypirc`, pip/uv/Poetry config/credential stores,
custom `PIP_CONFIG_FILE`, per-venv `pip.conf`, netrc and keyring files. Publishing
and package-auth environment overrides are denied, including TWINE, PIP, UV,
PYPI and Poetry credentials. Pip config loading and pip/uv/Python keyring lookup
are disabled inside the sandbox; credential files on the host remain unchanged.
The protected paths follow the documented [.pypirc format](https://packaging.python.org/en/latest/specifications/pypirc/),
[pip configuration sources](https://pip.pypa.io/en/stable/topics/configuration/),
and [uv credential sources](https://docs.astral.sh/uv/concepts/authentication/http/).
Do not place credentials in the writable workspace or deliberately exposed data.

The GitHub proxy is a temporary guard against **accidental writes**, with a
host-enforced command/option allowlist. Supported families are read-only PR,
issue, repository, search, release and run inspection. Unsupported commands and
options fail closed: raw API, downloads, templates, browser actions, auth changes,
PR/issue writes, merges, reviews, and workflow mutations are denied. GitHub writes
and attempts to bypass the proxy are off-limits to agents; denied actions belong
to the human. This is not adversarial isolation. Broader proxy hardening is future
work. The host token is not mounted into the sandbox.

The private sandbox-local `gh` adapter is cleaned up with the owned proxy and
socket after execution; installed public commands all use `sw-` names.

## Git review

```bash
sw-review -C /path/to/repo open TOPIC BASE
sw-review open TOPIC BASE --merge-base --no-browser
sw-review open TOPIC BASE --static review.html
sw-review comments REV --unresolved
sw-review add-comment REV --file src/example.py --line 42 --body 'Check this'
sw-review resolve REV COMMENT_ID
sw-review unresolve REV COMMENT_ID
sw-review verdict REV --verdict approve --body 'Looks good'
sw-review verdict REV --verdict request-changes --body 'Address feedback'
sw-review show REV
```

Global `-C/--repo` and `--author` options precede the subcommand. Works in any Git
repository, including subdirectories and linked worktrees; no workspace setup
is required. `REV` accepts branches, tags and commit IDs. Feedback commands
emit JSON; diagnostics go to stderr. Author priority: `--author`,
`SW_REVIEW_AUTHOR`, selected repository `user.name`, then `anonymous`. Git notes
writes require normal Git commit identity configuration.

Default comparison is endpoint `BASE..TOPIC`; `--merge-base` compares from the
fork point. Working-tree/index changes are excluded. The self-contained UI has
syntax highlighting, file navigation, inline left/right comments, resolution,
verdicts and j/k, n/N, ]/[ keyboard navigation. Click an old/new line number to
comment. Binary and mode-only changes are represented as metadata. Static
exports are read-only snapshots with persistence controls disabled.

Interactive serving binds `127.0.0.1`, prints the URL and opens a browser unless
`--no-browser` is passed. `--port 0` chooses a free port. Mutations require the
session token and matching origin/Host; the server serves no arbitrary files.
All feedback is pinned to the displayed topic commit, even if its branch moves.
Records include comparison context; feedback from other base comparisons is
labeled. CLI-created feedback has unspecified comparison context.

Storage is a versioned JSON document in **`refs/notes/sw-review`** on the reviewed
commit. There is no legacy migration or issue-tracker integration. Feedback and
approval do not follow new commits or rebases. Inspect an old commit explicitly;
do not transfer approval onto changed code. Malformed notes are errors and never
silently replaced. A shared Git-directory lock and conditional ref update retain
concurrent writes or report conflicts. POSIX file locking is required for writes.

Notes stay local unless explicitly synchronized. To publish deliberately:
`git push origin refs/notes/sw-review`. Fetch to a separate notes ref first if
histories may diverge, then inspect/merge deliberately. The tool performs no
implicit fetch, push, or notes merging.

## Installed agent guide and configuration

`sw-agent-readme` prints the concise full operating guide. Detail subcommands
are `init`, `sandbox`, `review`, and `config`; `--all` prints everything. Resources
are installed with the package, so agents need no local README or source checkout.

```toml
schema = 1
name = "example"

[sandbox]
network = true
gpu = true
gh_proxy = false
agent_profiles = []
ro = []
rw = []

[sandbox.env]
MY_SETTING = "value"
```

Unknown keys/types and invalid repository entries fail validation. CLI booleans
override configuration; mount flags append; agent-profile flags replace the
profile list. Sandbox control variables and runtime paths cannot be overridden
via sandbox.env. `sw-init --set` supports name and sandbox boolean/list fields;
edit repository tables and sandbox.env directly.

## Development and tests

```bash
python3 -m venv .venv
.venv/bin/python -m pip install -e '.[test]'
.venv/bin/python -m pytest
.venv/bin/python -m build --no-isolation
```

Tests use temporary workspaces/repositories, fake host services and real Git.
Ordinary tests require no network, GPU or external accounts. Packaging tests
build/install in a fresh venv and exercise source-free installed resources and
force-reinstallation. Optional Linux integration tests skip explicitly when host
namespace facilities are unavailable. Renderer/HTTP tests cover persistence,
validation and escaping; a browser smoke check complements automated tests.

Apache-2.0; see LICENSE and NOTICE. Review layout/styles are adapted from the
original local pyre-review project. HRX/ROCm-specific scripts, role/model launchers,
automatic source synchronization, and a general plugin framework are outside the
initial scope.


## Named interactive agents

Enable the optional roster and coordination files, then install the pinned
beads-rust tool and create a fresh tracker explicitly:

```bash
sw-init --team
sw-agent install-br --dry-run
sw-agent install-br
sw-agent init-beads
sw-agent doctor
sw-agent start lead
sw-agent visit lead
```

Requires Linux, Bubblewrap, tmux and a qualified Codex CLI (tested with 0.162.1).
The primordial `sw-init.py --team` also works before installing Python packages.
Initializer never starts agents or creates a tracker. Existing trackers are
preserved; migrations are explicit operator work.

Talk normally to the lead. Start the named workers once from the operator shell; the lead creates and
assigns beads through `sw-agent`, and running workers wake on ready assignments. Visit a
worker's actual Codex UI with `sw-agent visit ada`; this suspends automatic task
pickup until `sw-agent auto ada`. `sw-agent watch ada` observes without takeover.
Detaching tmux keeps the conversation running.

[docs/multi-agent.md](docs/multi-agent.md) is the living design and complete
operator reference, including machine-wide IT, MOTD broadcasts, cooperative
ownership, sandbox mounts and recovery. Installed agents use
`sw-agent-readme team` and `sw-agent-readme machine`.
