# Git notes review

Global options go before the subcommand: `sw-review [-C REPO] [--author NAME] ...`.
Repository selection supports subdirectories and linked worktrees, independently
of workspace setup. Requires Git; rendering additionally uses installed Pygments.

```
sw-review open TOPIC BASE [--merge-base] [--no-browser] [--port 0]
sw-review open TOPIC BASE --static review.html
sw-review comments REV [--unresolved]
sw-review show REV
sw-review add-comment REV --file FILE --line N --body TEXT [--side left|right]
sw-review resolve REV COMMENT_ID
sw-review unresolve REV COMMENT_ID
sw-review verdict REV --verdict approve --body TEXT
sw-review verdict REV --verdict request-changes --body TEXT
```

Endpoint comparison (BASE..TOPIC) is the default; --merge-base compares from the
fork point. No uncommitted/index changes are included. UI shows both commit IDs
and comparison mode. It binds 127.0.0.1, prints a URL, and optionally opens a
browser. Static export is a self-contained read-only snapshot; persistence
controls are disabled. Click old/new line numbers to comment on left/right.
Keyboard navigation: j/k files, n/N comments, ]/[ changes.

Browser writes pin the displayed commit and record base-comparison context.
Feedback from another comparison is labeled. CLI additions have unspecified
comparison context. show returns the versioned document; other feedback commands
return JSON records/lists. Diagnostics go to stderr. Author is --author, then
SW_REVIEW_AUTHOR, then selected repository user.name, then anonymous.

Notes use refs/notes/sw-review, schema 1. Commit-scoped feedback does not follow
new commits, rebases or branches; inspect old SHAs explicitly. Do not transfer
approvals onto changed code. Malformed/unsupported notes fail without overwriting.
Concurrent writers use a shared-worktree advisory lock and conditional ref update.
Mutation requires normal Git notes commit identity configuration (user.name and
user.email). Git object/ref failures are errors, not empty reviews.

No automatic network operations occur. To share notes intentionally:
`git push origin refs/notes/sw-review`; fetch to a separate notes ref first when
histories may diverge, inspect and merge deliberately. Ordinary clone/fetch/push
need not include notes. No issue tracker or automatic notes merging is provided.
