"""Checked Git operations and full-context diffs, independent of worktree state."""
from __future__ import annotations

from dataclasses import dataclass, field
import os
from pathlib import Path
import re
import subprocess


class ReviewError(ValueError):
    pass


def git(repo: Path, *args: str, input: bytes | None = None, check: bool = True) -> subprocess.CompletedProcess:
    env = {k: v for k, v in os.environ.items() if k not in {"GIT_DIR", "GIT_WORK_TREE", "GIT_INDEX_FILE", "GIT_COMMON_DIR", "GIT_EXTERNAL_DIFF"}}
    result = subprocess.run(["git", "-c", "core.pager=cat", "-c", "color.ui=false", *args],
                            cwd=repo, input=input, capture_output=True, env=env)
    if check and result.returncode:
        raise ReviewError(result.stderr.decode(errors="replace").strip() or f"Git failed: {args[0]}")
    return result


def find_repo(path: str | Path | None = None) -> Path:
    start = Path(path or Path.cwd()).expanduser().resolve()
    result = git(start, "rev-parse", "--show-toplevel")
    return Path(os.fsdecode(result.stdout.rstrip(b"\n")))


def resolve(repo: Path, rev: str) -> str:
    if not rev or "\x00" in rev:
        raise ReviewError("Revision must be nonempty")
    return git(repo, "rev-parse", "--verify", "--end-of-options", f"{rev}^{{commit}}").stdout.decode().strip()


@dataclass
class DiffLine:
    type: str
    old_lineno: int | None
    new_lineno: int | None
    content: str
    no_newline: bool = False


@dataclass
class FileDiff:
    path: str
    status: str
    old_path: str | None = None
    lines: list[DiffLine] = field(default_factory=list)
    additions: int = 0
    deletions: int = 0
    binary: bool = False
    metadata: str = ""


def comparison(repo: Path, topic: str, base: str, merge_base: bool = False) -> dict:
    head, endpoint = resolve(repo, topic), resolve(repo, base)
    effective = git(repo, "merge-base", endpoint, head).stdout.decode().strip() if merge_base else endpoint
    return {"commit": head, "base": effective, "requested_base": endpoint,
            "mode": "merge-base" if merge_base else "endpoints"}


def get_diff_files(repo: Path, head: str, base: str) -> list[FileDiff]:
    raw = git(repo, "diff", "--no-ext-diff", "--no-textconv", "--name-status", "-z", "-M", base, head, "--").stdout
    tokens = raw.split(b"\0")
    files, i = [], 0
    while i < len(tokens) and tokens[i]:
        status = tokens[i].decode()
        old = os.fsdecode(tokens[i + 1])
        i += 2
        path = old
        if status[0] in "RC":
            path = os.fsdecode(tokens[i])
            i += 1
        fd = FileDiff(path, status[0], old if old != path else None)
        patch = git(repo, "--literal-pathspecs", "diff", "--no-ext-diff", "--no-textconv", "--no-color",
                    "-M", "-U99999", base, head, "--", *dict.fromkeys([old, path])).stdout.decode(errors="replace")
        fd.binary = "\nBinary files " in patch or "\nGIT binary patch" in patch
        in_hunk, old_n, new_n = False, 0, 0
        metadata = []
        for line in patch.split("\n"):
            if line.startswith("@@ "):
                match = re.match(r"@@ -(\d+)(?:,\d+)? \+(\d+)(?:,\d+)? @@", line)
                if match:
                    old_n, new_n = map(int, match.groups())
                    in_hunk = True
                continue
            if not in_hunk:
                if not line.startswith(("diff --git", "index ", "--- ", "+++ ")):
                    metadata.append(line)
                continue
            if line.startswith("\\ No newline"):
                if fd.lines:
                    fd.lines[-1].no_newline = True
            elif line.startswith("+"):
                fd.lines.append(DiffLine("added", None, new_n, line[1:]))
                fd.additions += 1
                new_n += 1
            elif line.startswith("-"):
                fd.lines.append(DiffLine("deleted", old_n, None, line[1:]))
                fd.deletions += 1
                old_n += 1
            elif line.startswith(" "):
                fd.lines.append(DiffLine("context", old_n, new_n, line[1:]))
                old_n += 1
                new_n += 1
        fd.metadata = "\n".join(metadata)
        files.append(fd)
    return files


def get_log(repo: Path, head: str, base: str) -> list[dict]:
    out = git(repo, "log", "--format=%H%x00%an%x00%aI%x00%s%x00", f"{base}..{head}", "--").stdout
    fields = out.decode(errors="replace").split("\0")
    return [dict(zip(("sha", "author", "date", "subject"), [fields[i].lstrip("\n"), *fields[i + 1:i + 4]]))
            for i in range(0, len(fields) - 4, 4)]
