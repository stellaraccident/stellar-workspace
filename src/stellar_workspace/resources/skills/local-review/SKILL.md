---
name: local-review
description: Open local Git reviews and read or update commit-scoped feedback using sw-review.
---

Use `sw-review -C REPO open TOPIC BASE --no-browser` to print a loopback URL, or
omit `--no-browser` for browser launch. Endpoint comparison is the default;
`--merge-base` reviews changes since the fork. The UI writes to the displayed
commit even if the branch advances. `--static FILE` exports a read-only snapshot.

Use `comments REV --unresolved`, `add-comment REV --file FILE --line N --body
TEXT`, `resolve REV ID`, `unresolve REV ID`, and `show REV` for JSON feedback.
Record a verdict with `verdict REV --verdict approve|request-changes --body TEXT`.
Run `sw-review --help` for full syntax and author options.

Notes live at `refs/notes/sw-review`, locally unless explicitly synchronized.
Feedback never follows new commits/rebases automatically. Read the old commit
explicitly; do not carry approval to changed code. Resolve feedback only after
addressing it. No issue tracker or implicit push is involved.
