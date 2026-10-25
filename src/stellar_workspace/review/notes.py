"""Versioned notes with a shared-worktree lock and compare-and-swap ref update."""
from __future__ import annotations

from contextlib import contextmanager
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import re
import secrets
import time

from .git_ops import ReviewError, git, resolve

REF = "refs/notes/sw-review"


def read(repo: Path, sha: str) -> dict:
    result = git(repo, "notes", "--ref", REF, "show", sha, check=False)
    if result.returncode:
        # Missing note is normal, errors in an existing notes tree are not.
        listing = git(repo, "notes", "--ref", REF, "list")
        if any(line.split()[-1] == sha.encode() for line in listing.stdout.splitlines()):
            raise ReviewError(result.stderr.decode(errors="replace"))
        return {"schema": 1, "commit": sha, "records": []}
    try:
        data = json.loads(result.stdout)
        if not isinstance(data, dict) or data.get("schema") != 1 or data.get("commit") != sha or not isinstance(data.get("records"), list):
            raise ValueError("unsupported schema/commit")
        seen = set()
        for record in data["records"]:
            if not isinstance(record, dict) or record.get("type") not in {"comment", "verdict"}:
                raise ValueError("invalid record")
            if not re.fullmatch(r"r_[0-9a-f]{32}", record.get("id", "")) or record["id"] in seen:
                raise ValueError("invalid/duplicate record id")
            seen.add(record["id"])
            for field in ("author", "timestamp", "body"):
                if not isinstance(record.get(field), str):
                    raise ValueError(f"invalid record {field}")
            if record["type"] == "comment":
                validate_comment(record)
                if type(record.get("resolved")) is not bool:
                    raise ValueError("invalid resolution")
            elif record.get("verdict") not in {"approve", "request-changes"}:
                raise ValueError("invalid verdict")
            context = record.get("context")
            if context is not None and (not isinstance(context, dict) or context.get("commit") != sha
                                        or context.get("mode") not in {"endpoints", "merge-base"}
                                        or not re.fullmatch(r"[0-9a-f]{40,64}", context.get("base", ""))):
                raise ValueError("invalid comparison context")
        return data
    except (ValueError, TypeError, KeyError) as exc:
        raise ReviewError(f"Invalid review note on {sha}: {exc}; refusing to overwrite") from exc


@contextmanager
def lock(repo: Path):
    import fcntl
    common = git(repo, "rev-parse", "--git-common-dir").stdout.decode().strip()
    directory = (repo / common).resolve()
    with (directory / "sw-review.lock").open("a+b") as handle:
        deadline = time.monotonic() + 10
        while True:
            try:
                fcntl.flock(handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
                break
            except BlockingIOError:
                if time.monotonic() > deadline:
                    raise ReviewError("Timed out waiting for another review writer")
                time.sleep(0.02)
        try:
            yield
        finally:
            fcntl.flock(handle, fcntl.LOCK_UN)


def update(repo: Path, sha: str, mutate):
    with lock(repo):
        old_result = git(repo, "rev-parse", "--verify", REF, check=False)
        old = old_result.stdout.decode().strip() if old_result.returncode == 0 else ""
        data = read(repo, sha)
        result = mutate(data["records"])
        temporary = f"refs/notes/sw-review-tmp/{secrets.token_hex(16)}"
        try:
            if old:
                git(repo, "update-ref", temporary, old)
            git(repo, "notes", "--ref", temporary, "add", "-f", "-F", "-", sha,
                input=json.dumps(data, indent=2).encode())
            new = git(repo, "rev-parse", "--verify", temporary).stdout.decode().strip()
            git(repo, "update-ref", REF, new, old or "0" * len(new))
        finally:
            git(repo, "update-ref", "-d", temporary, check=False)
        return result


def author(repo: Path, explicit: str | None = None) -> str:
    name = explicit or os.environ.get("SW_REVIEW_AUTHOR")
    if not name:
        name = git(repo, "config", "user.name", check=False).stdout.decode(errors="replace").strip() or "anonymous"
    if not isinstance(name, str) or not name.strip() or len(name) > 500:
        raise ReviewError("Invalid author")
    return name


def validate_comment(body: dict):
    if not isinstance(body.get("file"), str) or not body["file"] or "\x00" in body["file"] or Path(body["file"]).is_absolute() or ".." in Path(body["file"]).parts:
        raise ReviewError("Comment file must be a repository-relative path")
    if type(body.get("line")) is not int or body["line"] < 1:
        raise ReviewError("Comment line must be a positive integer")
    if body.get("side", "right") not in {"left", "right"}:
        raise ReviewError("Comment side must be left or right")
    if not isinstance(body.get("body"), str) or not body["body"].strip() or len(body["body"]) > 100_000:
        raise ReviewError("Comment body must contain 1..100000 characters")


def add(repo: Path, sha: str, body: dict, who: str, context=None, verdict=False):
    if verdict:
        if body.get("verdict") not in {"approve", "request-changes"} or not isinstance(body.get("body", ""), str) or len(body.get("body", "")) > 100_000:
            raise ReviewError("Invalid verdict or body")
        fields = {"verdict": body["verdict"], "body": body.get("body", "")}
    else:
        validate_comment(body)
        fields = {k: body[k] for k in ("file", "line", "body")}
        fields.update(side=body.get("side", "right"), resolved=False, resolved_by=None, resolved_at=None)
    record = {"id": "r_" + secrets.token_hex(16), "type": "verdict" if verdict else "comment",
              "author": who, "timestamp": datetime.now(timezone.utc).isoformat(), "context": context, **fields}
    def mutate(records):
        records.append(record)
        return record
    return update(repo, sha, mutate)


def resolution(repo: Path, sha: str, identifier: str, value: bool, who: str):
    if not re.fullmatch(r"r_[0-9a-f]{32}", identifier):
        raise ReviewError("Invalid comment id")
    def mutate(records):
        for record in records:
            if record["id"] == identifier and record["type"] == "comment":
                record.update(resolved=value, resolved_by=who if value else None,
                              resolved_at=datetime.now(timezone.utc).isoformat() if value else None)
                return record
        raise ReviewError(f"Comment not found: {identifier}")
    return update(repo, sha, mutate)
