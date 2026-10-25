# Configuration

workspace.toml is the marker; schema 1 requires a nonempty name. Discovery uses
--workspace (sandbox), then SW_WORKSPACE, then nearest marker above cwd. Explicit
invalid roots fail. Initial creation uses PATH/cwd; maintenance discovers roots.
Relative configured mounts use the workspace root. Unknown keys/types fail.

```toml
schema = 1
name = "example"

[sandbox]
network = true
gpu = true
gh_proxy = false
agent_profiles = [] # codex
ro = []
rw = []

[sandbox.env]
MY_TOOL_SETTING = "value"

[[repositories]]
name = "example-source"
path = "sources/example-source"
remote = "https://example.org/team/example-source.git"
branch = "main"
```

Repositories are descriptive independent checkouts, not submodules. Names/paths
must be unique; paths must be under sources/. Initializer never synchronizes them.

`sw-init --set KEY VALUE` supports name and sandbox boolean/list fields. VALUE
uses JSON syntax for booleans/lists; plain strings work for name. It preserves
comments and unrelated fields. Complex/multiline field representations and other
edits (repository tables, sandbox.env) require direct TOML editing; ambiguous
rewrites are rejected. Existing config is retained during template upgrades.
Environment overrides must be string pairs; sandbox control/runtime paths and
code-injection variables cannot be overridden using sandbox.env.

Managed template hashes live in .sw/managed.json; runtime paths are untracked.
Python minimum is 3.11. Toolset installation only updates the selected venv;
run sw-init --upgrade explicitly to apply new managed templates.
