---
name: add-repository
description: Add a user-requested independent source repository to this workspace and its tracked catalog.
---

Inspect `workspace.toml`, root `.gitignore`, and any existing destination before
adding a repository. Check status in existing checkouts. Choose a path under
`sources/` and an explicit branch consistent with the user's request; clarify
an ambiguous branch before making branch changes. Do not replace a directory,
reset a checkout, or infer permission to commit/push.

For a requested new checkout, clone into `sources/NAME/`. Keep its `.git`
independent; do not vendor files or create a submodule. Add descriptive tracked
metadata to `workspace.toml`:

```toml
[[repositories]]
name = "example"
path = "sources/example"
remote = "https://example.org/team/example.git"
branch = "main"
```

Initialization never automatically clones or synchronizes this catalog. Verify
remote, branch and Git status against the entry and confirm the root ignores
the checkout. Update local README/AGENTS project context as needed. Avoid
changing generated generic instructions. Summarize the checkout and metadata
changes; leave commits and publication to the requested workflow.
