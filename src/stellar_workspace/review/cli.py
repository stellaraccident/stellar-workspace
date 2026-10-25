"""Local browser review and JSON feedback stored in commit-scoped Git notes."""
import argparse
import json
from pathlib import Path
import sys

from . import git_ops, notes


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("-C", "--repo", help="Repository (default: current directory)")
    parser.add_argument("--author", help="Override SW_REVIEW_AUTHOR / repository user.name")
    sub = parser.add_subparsers(dest="command", required=True)
    p = sub.add_parser("open", help="Open browser review or export a static snapshot")
    p.add_argument("topic")
    p.add_argument("base")
    p.add_argument("--merge-base", action="store_true")
    p.add_argument("--port", type=int, default=0)
    p.add_argument("--no-browser", action="store_true")
    p.add_argument("--static", metavar="FILE")
    for name in ("comments", "show", "add-comment", "resolve", "unresolve", "verdict"):
        p = sub.add_parser(name)
        p.add_argument("rev")
        if name == "comments":
            p.add_argument("--unresolved", action="store_true")
        elif name == "add-comment":
            p.add_argument("--file", required=True)
            p.add_argument("--line", required=True, type=int)
            p.add_argument("--body", required=True)
            p.add_argument("--side", choices=["left", "right"], default="right")
        elif name in ("resolve", "unresolve"):
            p.add_argument("comment_id")
        elif name == "verdict":
            p.add_argument("--verdict", required=True, choices=["approve", "request-changes"])
            p.add_argument("--body", default="")
    args = parser.parse_args(argv)
    try:
        repo = git_ops.find_repo(args.repo)
        if args.command == "open":
            if not 0 <= args.port <= 65535:
                raise git_ops.ReviewError("Port must be between 0 and 65535")
            context = git_ops.comparison(repo, args.topic, args.base, args.merge_base)
            diffs = git_ops.get_diff_files(repo, context["commit"], context["base"])
            records = notes.read(repo, context["commit"])["records"]
            commits = git_ops.get_log(repo, context["commit"], context["base"])
            from .generate import generate_html
            if args.static:
                Path(args.static).write_text(generate_html(diffs, records, args.topic, args.base, commits, context), encoding="utf-8")
                print(f"Static read-only review written to {args.static}")
            else:
                from .server import make_server, run_server
                server = make_server(repo, context, diffs, records, args.topic, args.base, commits, notes.author(repo, args.author), args.port)
                run_server(server, args.no_browser)
            return 0
        sha = git_ops.resolve(repo, args.rev)
        if args.command in ("show", "comments"):
            result = notes.read(repo, sha)
            if args.command == "comments":
                result = [r for r in result["records"] if r["type"] == "comment" and (not args.unresolved or not r["resolved"])]
        elif args.command in ("add-comment", "verdict"):
            result = notes.add(repo, sha, vars(args), notes.author(repo, args.author), verdict=args.command == "verdict")
        else:
            result = notes.resolution(repo, sha, args.comment_id, args.command == "resolve", notes.author(repo, args.author))
        print(json.dumps(result, indent=2))
        return 0
    except (git_ops.ReviewError, OSError, ValueError) as exc:
        print(f"sw-review: {exc}", file=sys.stderr)
        return 1
