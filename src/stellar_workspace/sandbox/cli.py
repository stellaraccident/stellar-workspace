"""Run a command or interactive shell in a Linux Bubblewrap workspace sandbox."""
import argparse
import json
import sys
from ..workspace import WorkspaceError, discover, load
from .core import build_plan, execute, payload_command


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--workspace")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--network", action=argparse.BooleanOptionalAction, default=None)
    parser.add_argument("--gpu", action=argparse.BooleanOptionalAction, default=None)
    parser.add_argument("--gh-proxy", action=argparse.BooleanOptionalAction, default=None)
    parser.add_argument("--agent-profile", action="append", choices=["codex"])
    parser.add_argument("--agent-name", help="Use isolated state for this named Codex agent")
    parser.add_argument("--ro", action="append")
    parser.add_argument("--rw", action="append")
    parser.add_argument("--dev", action="append", metavar="PATH",
                        help="Add a device mount using Bubblewrap --dev-bind (repeatable)")
    parser.add_argument("--cap-add", action="append", metavar="CAP",
                        help="Retain a capability in the sandbox user namespace (repeatable)")
    parser.add_argument("--fuse", action="store_true",
                        help="Enable FUSE: implies --dev /dev/fuse --cap-add CAP_SYS_ADMIN")
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
        for k in ("ro", "rw", "dev", "cap_add"):
            if getattr(args, k):
                overrides[k] = config.get("sandbox", {}).get(k, []) + getattr(args, k)
        if args.fuse:
            overrides["fuse"] = True
            for key, value in (("dev", "/dev/fuse"), ("cap_add", "CAP_SYS_ADMIN")):
                values = list(overrides.get(key, config.get("sandbox", {}).get(key, [])))
                if value not in values:
                    values.append(value)
                overrides[key] = values
        plan = build_plan(root, config, overrides, agent_name=args.agent_name)
        command = args.command[1:] if args.command[:1] == ["--"] else args.command
        if args.dry_run:
            print(json.dumps({**plan.as_dict(), "command": payload_command(plan, command or ["bash (interactive)"])}, indent=2))
            return 0
        print("Sandbox capabilities: " + json.dumps(plan.capabilities), file=sys.stderr)
        return execute(plan, command)
    except (WorkspaceError, OSError, ValueError) as exc:
        print(f"sw-sandbox: {exc}", file=sys.stderr)
        return 1
