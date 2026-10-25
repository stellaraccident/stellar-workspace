"""Dependency-free workspace bootstrap and managed-file maintenance."""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import difflib
import hashlib
from importlib.resources import files
import json
import os
from pathlib import Path
import shutil
import sys
import tempfile
import tomllib

from . import __version__
from .workspace import WorkspaceError, discover, load, set_values, validate

DIRECTORIES = ("sources", "docs", "skills", "tools", "build", "cache", "programs/bin", ".tmp", "scratch")
STATE = ".sw/managed.json"


def digest(text: str) -> str:
    return hashlib.sha256(text.encode()).hexdigest()


def templates(name: str, source: str) -> dict[str, str]:
    resources = files("stellar_workspace").joinpath("resources")
    result = {"workspace.toml": f"schema = 1\nname = {json.dumps(name)}\n\n[sandbox]\nnetwork = true\ngpu = true\ngh_proxy = false\nagent_profiles = []\nro = []\nrw = []\n"}
    for target, resource in (("AGENTS.md", "workspace-agents.md"), ("README.md", "workspace-readme.md"),
                             (".envrc", "envrc.sh"), (".gitignore", "workspace-ignore.md")):
        result[target] = resources.joinpath(resource).read_text().replace("__NAME__", name).replace("__SOURCE__", source)
    for skill in ("add-repository", "workspace-environment", "sandbox-workflow", "local-review"):
        result[f"skills/{skill}/SKILL.md"] = resources.joinpath("skills", skill, "SKILL.md").read_text()
    return result


def contained(root: Path, rel: str) -> Path:
    path = root / rel
    if path.is_symlink() or any(p.is_symlink() for p in path.parents if p != root and root in p.parents):
        raise WorkspaceError(f"Refusing symlinked managed path: {path}")
    for parent in path.parents:
        if parent == root:
            break
        if parent.exists() and not parent.is_dir():
            raise WorkspaceError(f"Expected directory: {parent}")
    if not path.resolve().is_relative_to(root):
        raise WorkspaceError(f"Managed path escapes workspace: {path}")
    return path


def atomic_write(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, name = tempfile.mkstemp(prefix=".sw-write-", dir=path.parent)
    try:
        os.fchmod(fd, (path.stat().st_mode & 0o777) if path.exists() else 0o644)
        with os.fdopen(fd, "w", encoding="utf-8") as stream:
            stream.write(content)
        os.replace(name, path)
    finally:
        Path(name).unlink(missing_ok=True)


def initialize(root: Path, *, name: str | None = None, source: str | None = None,
               upgrade: bool = False, repair: bool = False, changes: list | None = None,
               dry_run: bool = False, team: bool = False) -> list[str]:
    if root.is_symlink():
        raise WorkspaceError(f"Workspace destination is a symlink: {root}")
    root = root.absolute()
    if any(parent.is_symlink() for parent in root.parents):
        raise WorkspaceError("Workspace destination has a symlinked ancestor")
    root = root.resolve()
    state_path = contained(root, STATE)
    state = {"schema": 1, "files": {}, "source": source or ""}
    if state_path.exists():
        try:
            state = json.loads(state_path.read_text())
            if state["schema"] != 1 or not isinstance(state["files"], dict):
                raise ValueError("unsupported provenance")
        except (ValueError, KeyError, TypeError) as exc:
            raise WorkspaceError(f"Invalid {state_path}: {exc}") from exc
    config = {}
    config_path = contained(root, "workspace.toml")
    if config_path.exists():
        config = load(root)
        name = name or config["name"]
    elif upgrade or repair or changes:
        if "workspace.toml" not in state["files"] or not repair:
            raise WorkspaceError("Maintenance requires an initialized workspace")
    name = name or state.get("name") or root.name
    if not name.strip() or "\n" in name or "\r" in name:
        raise WorkspaceError("Workspace name must be nonempty and single-line")
    source = source or state.get("source") or "<canonical-source-checkout>"
    config_text = None
    if config_path.exists():
        edits = list(changes or [])
        if name != config["name"]:
            edits.append(["name", name])
        config_text = set_values(config_path.read_text(), edits)
        name = validate(tomllib.loads(config_text))["name"]
    desired = templates(name, source)
    if config_text is not None:
        desired["workspace.toml"] = config_text
    elif changes:
        desired["workspace.toml"] = set_values(desired["workspace.toml"], changes)
    if team and "team" not in tomllib.loads(desired["workspace.toml"]):
        from .agents.config import team_text
        desired["workspace.toml"] += team_text()
    final_config = validate(tomllib.loads(desired["workspace.toml"]))
    if "team" in final_config:
        from .agents.config import team_templates
        desired.update(team_templates(final_config["team"]))
        desired["AGENTS.md"] += ("\n## Named team\n\nRead `sw-agent-readme team` and `sw-agent-readme machine`. "
            "The roster is in workspace.toml; personal instructions are in agents/NAME/AGENTS.md. "
            "Read workspace and shared MOTDs before new work. "
            "Use sw-agent for canonical beads and named sessions; respect peer ownership.\n\n"
            "- [Team operation](skills/team-operation/SKILL.md)\n"
            "- [Machine operation](skills/machine-operation/SKILL.md)\n")
        desired[".gitignore"] += "\n/agents/*/state/\n/agents/*/logs/\n/agents/*/worktrees/\n/agents/*/build/\n/agents/*/cache/\n/agents/*/programs/\n/agents/*/scratch/\n/agents/*/tmp/\n/.sw/agents/\n"
    conflicts, writes, plan = [], {}, []
    new_files = dict(state["files"])
    for directory in (*DIRECTORIES, ".sw"):
        path = contained(root, directory)
        if path.exists() and not path.is_dir():
            conflicts.append(f"Expected directory: {path}")
        elif not path.exists():
            plan.append(f"mkdir {directory}/")
    for rel, text in desired.items():
        path = contained(root, rel)
        recorded = state["files"].get(rel)
        if path.exists() and not path.is_file():
            conflicts.append(f"Expected file: {path}")
            continue
        old = path.read_text() if path.exists() else None
        if old == text:
            # Do not silently adopt preexisting unmanaged files.
            if recorded or not config_path.exists():
                new_files[rel] = digest(text)
            continue
        change = old is None or (rel == "workspace.toml" and bool(changes or team or name != config.get("name", name))) or upgrade or (team and rel in {".gitignore", "AGENTS.md"}) or (rel in {"AGENTS.md", "README.md"} and name != state.get("name", name))
        if old is not None and change and (not recorded or (rel != "workspace.toml" and digest(old) != recorded)):
            difference = "".join(difflib.unified_diff(old.splitlines(True), text.splitlines(True), fromfile=rel, tofile=f"{rel} (proposed)"))
            conflicts.append(f"Customized or unmanaged file: {rel}\n{difference}")
        elif change:
            writes[rel] = text
            new_files[rel] = digest(text)
            plan.append(f"{'create' if old is None else 'update'} {rel}")
            if old is not None:
                plan.append("".join(difflib.unified_diff(old.splitlines(True), text.splitlines(True), fromfile=rel, tofile=rel)))
    if conflicts:
        raise WorkspaceError("Conflicting plan; no changes made:\n" + "\n".join(conflicts))
    new_state = {"schema": 1, "tool_version": __version__, "name": name, "source": source, "files": new_files}
    state_text = json.dumps(new_state, indent=2, sort_keys=True) + "\n"
    if not state_path.exists() or state_path.read_text() != state_text:
        writes[STATE] = state_text
        plan.append(f"update {STATE}")
    if not dry_run:
        backup = root / ".tmp" / "sw-init-backups" / datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S.%fZ")
        for rel in writes:
            path = contained(root, rel)
            if path.exists():
                dest = contained(root, str(backup.relative_to(root) / rel))
                dest.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(path, dest)
        try:
            for directory in DIRECTORIES:
                contained(root, directory).mkdir(parents=True, exist_ok=True)
            for rel, text in writes.items():
                atomic_write(contained(root, rel), text)
        except OSError as exc:
            raise WorkspaceError(f"Partial initialization: {exc}; original files saved under {backup}; rerun --repair after resolving the error") from exc
    return plan


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("path", nargs="?")
    parser.add_argument("--name")
    modes = parser.add_mutually_exclusive_group()
    modes.add_argument("--upgrade", action="store_true")
    modes.add_argument("--repair", action="store_true")
    parser.add_argument("--set", nargs=2, action="append", default=[], metavar=("KEY", "VALUE"))
    parser.add_argument("--team", action="store_true", help="Add managed team roster, MOTD, instructions and skills")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args(argv)
    try:
        root = Path(args.path).expanduser() if args.path else (discover() if args.upgrade or args.repair or args.set else Path.cwd())
        checkout = Path(__file__).resolve().parents[2]
        source = str(checkout) if (checkout / "sw-init.py").exists() else None
        plan = initialize(root, name=args.name, source=source, upgrade=args.upgrade, repair=args.repair,
                          changes=args.set, dry_run=args.dry_run, team=args.team)
        print("\n".join(plan) if plan else "Workspace is up to date.")
        print(f"\nNext: cd {str(root)!r}, then run direnv allow from your external shell.")
        import shlex
        canonical = source
        state_file = root / STATE
        if not canonical and state_file.is_file():
            canonical = json.loads(state_file.read_text()).get("source")
        print("After activation, install with: python -m pip install " + shlex.quote(canonical or "<canonical-source-checkout>"))
        return 0
    except (WorkspaceError, OSError, ValueError) as exc:
        print(f"sw-init: {exc}", file=sys.stderr)
        return 1
