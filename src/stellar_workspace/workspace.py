"""Workspace discovery and the versioned, data-only configuration contract."""
from __future__ import annotations

import json
import os
from pathlib import Path
import tomllib


class WorkspaceError(ValueError):
    pass


SANDBOX_DEFAULTS = {
    "network": True, "gpu": False, "gh_proxy": False,
    "agent_profiles": [], "ro": [], "rw": [], "env": {},
}


def validate(data: dict) -> dict:
    unknown = data.keys() - {"schema", "name", "sandbox", "repositories"}
    if unknown:
        raise WorkspaceError(f"Unknown workspace keys: {sorted(unknown)}")
    if type(data.get("schema")) is not int or data["schema"] != 1:
        raise WorkspaceError("Unsupported workspace schema; expected schema = 1")
    if not isinstance(data.get("name"), str) or not data["name"].strip():
        raise WorkspaceError("Workspace name must be a nonempty string")
    sandbox = data.get("sandbox", {})
    if not isinstance(sandbox, dict) or sandbox.keys() - SANDBOX_DEFAULTS.keys():
        raise WorkspaceError("Unknown or invalid sandbox configuration")
    for key, value in sandbox.items():
        if type(value) is not type(SANDBOX_DEFAULTS[key]):
            raise WorkspaceError(f"Invalid sandbox.{key} type")
        if isinstance(value, list) and any(not isinstance(x, str) for x in value):
            raise WorkspaceError(f"sandbox.{key} must contain strings")
    if set(sandbox.get("agent_profiles", [])) - {"codex", "claude"}:
        raise WorkspaceError("Agent profiles must be codex or claude")
    if any(not isinstance(k, str) or not isinstance(v, str) for k, v in sandbox.get("env", {}).items()):
        raise WorkspaceError("sandbox.env must map strings to strings")
    repos = data.get("repositories", [])
    if not isinstance(repos, list):
        raise WorkspaceError("repositories must be an array of tables")
    names, paths = set(), set()
    for repo in repos:
        if not isinstance(repo, dict) or set(repo) != {"name", "path", "remote", "branch"}:
            raise WorkspaceError("Each repository requires name, path, remote and branch")
        if any(not isinstance(v, str) or not v.strip() for v in repo.values()):
            raise WorkspaceError("Repository fields must be nonempty strings")
        path = Path(repo["path"])
        if path.is_absolute() or ".." in path.parts or len(path.parts) < 2 or path.parts[0] != "sources":
            raise WorkspaceError("Repository paths must be inside sources/")
        if repo["name"] in names or repo["path"] in paths:
            raise WorkspaceError("Duplicate repository name/path")
        names.add(repo["name"])
        paths.add(repo["path"])
    return data


def load(root: Path) -> dict:
    try:
        return validate(tomllib.loads((root / "workspace.toml").read_text()))
    except (OSError, tomllib.TOMLDecodeError) as exc:
        raise WorkspaceError(f"Cannot load {root / 'workspace.toml'}: {exc}") from exc


def discover(explicit: str | Path | None = None) -> Path:
    override = explicit or os.environ.get("SW_WORKSPACE")
    if override:
        root = Path(override).expanduser().resolve()
        load(root)
        return root
    here = Path.cwd().resolve()
    for path in (here, *here.parents):
        if (path / "workspace.toml").is_file():
            load(path)
            return path
    raise WorkspaceError("No workspace.toml found; run sw-init or pass --workspace PATH")


def set_values(text: str, changes: list[list[str]]) -> str:
    """Edit supported single-line TOML fields while preserving unrelated comments.

    This deliberately rejects complex/multiline representations instead of
    attempting a lossy general-purpose TOML rewrite during primordial bootstrap.
    """
    import re
    allowed = {"name"} | {f"sandbox.{k}" for k in SANDBOX_DEFAULTS if k != "env"}
    for key, raw in changes:
        if key not in allowed:
            raise WorkspaceError(f"Unsupported --set key: {key}; edit workspace.toml directly")
        try:
            value = json.loads(raw)
        except json.JSONDecodeError:
            value = raw
        section, _, field = key.rpartition(".")
        lines = text.splitlines(keepends=True)
        start, end = 0, len(lines)
        if section:
            headers = [(i, m.group(1).strip()) for i, line in enumerate(lines)
                       if (m := re.match(r"^\s*\[([^\[\]]+)\]\s*(?:#.*)?$", line))]
            found = next((i for i, s in headers if s == section), None)
            if found is None:
                text += f"\n[{section}]\n{field} = {json.dumps(value)}\n"
                validate(tomllib.loads(text))
                continue
            start = found + 1
        for i in range(start, len(lines)):
            if lines[i].lstrip().startswith("["):
                end = i
                break
        matches = [i for i in range(start, end) if re.match(rf"^\s*{re.escape(field)}\s*=", lines[i])]
        encoded = json.dumps(value, ensure_ascii=True)
        if matches:
            i = matches[0]
            # Recognize only values we can safely replace on a single line.
            match = re.fullmatch(r'(\s*\w+\s*=\s*)("(?:[^"\\]|\\.)*"|true|false|\[[^\n]*\])([ \t]*(?:#.*)?)(\n?)', lines[i])
            if not match:
                raise WorkspaceError(f"Edit {key} directly: unsupported TOML representation")
            lines[i] = f"{match[1]}{encoded}{match[3]}\n"
        else:
            lines.insert(end, f"{field} = {encoded}\n")
        text = "".join(lines)
        validate(tomllib.loads(text))
    return text
