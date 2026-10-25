"""Run a command or interactive shell in a Linux Bubblewrap workspace sandbox."""
import argparse
import json
import sys
from ..workspace import WorkspaceError, discover, load
from .core import build_plan, execute


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--workspace")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--network", action=argparse.BooleanOptionalAction, default=None)
    parser.add_argument("--gpu", action=argparse.BooleanOptionalAction, default=None)
    parser.add_argument("--gh-proxy", action=argparse.BooleanOptionalAction, default=None)
    parser.add_argument("--agent-profile", action="append", choices=["codex", "claude"])
    parser.add_argument("--ro", action="append")
    parser.add_argument("--rw", action="append")
    parser.add_argument("command", nargs=argparse.REMAINDER)
    args = parser.parse_args(argv)
    try:
        if sys.platform != "linux":
            raise WorkspaceError("sw-sandbox supports Linux only")
        root = discover(args.workspace)
        config = load(root)
        overrides = {k: getattr(args, k) for k in ("network", "gpu", "gh_proxy") if getattr(args, k) is not None}
        if args.agent_profile is not None:
            overrides["agent_profiles"] = args.agent_profile
        for k in ("ro", "rw"):
            if getattr(args, k):
                overrides[k] = config.get("sandbox", {}).get(k, []) + getattr(args, k)
        plan = build_plan(root, config, overrides)
        command = args.command[1:] if args.command[:1] == ["--"] else args.command
        if args.dry_run:
            print(json.dumps({**plan.as_dict(), "command": command or ["bash (interactive)"]}, indent=2))
            return 0
        print("Sandbox capabilities: " + json.dumps(plan.capabilities), file=sys.stderr)
        return execute(plan, command)
    except (WorkspaceError, OSError, ValueError) as exc:
        print(f"sw-sandbox: {exc}", file=sys.stderr)
        return 1
