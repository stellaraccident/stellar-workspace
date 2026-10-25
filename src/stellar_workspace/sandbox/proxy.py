"""Small host-side GitHub read proxy. Guards accidents, not hostile clients."""
from __future__ import annotations

import json
import os
from pathlib import Path
import socket
import socketserver
import subprocess
import threading

from .credentials import TOKEN_VARIABLES, secret_values


LIMIT = 1024 * 1024
COMMANDS = {
    ("pr", "list"), ("pr", "view"), ("pr", "diff"), ("pr", "checks"), ("pr", "status"),
    ("issue", "list"), ("issue", "view"), ("issue", "status"),
    ("repo", "view"), ("repo", "list"),
    ("search", "issues"), ("search", "prs"), ("search", "repos"), ("search", "code"),
    ("release", "list"), ("release", "view"), ("run", "list"), ("run", "view"),
}
# Command-specific option allowlists. In particular no --web, --watch, --comments
# mutations, --template, --jq, --output, --log-failed downloads, or raw API.
COMMON = {"--repo", "-R", "--json"}
VALUES = {
    ("pr", "list"): {"--state", "--base", "--head", "--author", "--assignee", "--label", "--search", "--limit"},
    ("pr", "view"): set(), ("pr", "diff"): set(), ("pr", "checks"): set(), ("pr", "status"): set(),
    ("issue", "list"): {"--state", "--author", "--assignee", "--label", "--search", "--limit"},
    ("issue", "view"): set(), ("issue", "status"): set(),
    ("repo", "view"): set(), ("repo", "list"): {"--limit", "--visibility", "--language", "--topic"},
    ("release", "list"): {"--limit"}, ("release", "view"): set(),
    ("run", "list"): {"--limit", "--branch", "--commit", "--event", "--status", "--user", "--workflow"},
    ("run", "view"): {"--job", "--attempt"},
}
SWITCHES = {
    ("pr", "view"): {"--comments"}, ("pr", "diff"): {"--patch", "--name-only"},
    ("issue", "view"): {"--comments"}, ("run", "view"): {"--verbose"},
}


def allowed(args: list[str]) -> bool:
    if not isinstance(args, list) or len(args) < 2 or len(args) > 100:
        return False
    if any(not isinstance(a, str) or not a or len(a) > 8192 or any(ord(c) < 32 for c in a) for a in args):
        return False
    command = tuple(args[:2])
    if command not in COMMANDS:
        return False
    values = COMMON | VALUES.get(command, set())
    if command[0] == "search":
        values |= {"--limit", "--owner", "--language", "--match", "--state", "--author"}
    # At most one identifier/query, and only where supported.
    max_pos = 1 if command[1] in {"view", "diff", "checks"} or command[0] == "search" or command == ("repo", "list") else 0
    positional, i = 0, 2
    while i < len(args):
        arg = args[i]
        if arg.startswith("-"):
            flag, sep, val = arg.partition("=")
            if flag in values:
                if not sep:
                    i += 1
                    if i >= len(args):
                        return False
                    val = args[i]
                if not val or val.startswith("-"):
                    return False
            elif arg not in SWITCHES.get(command, set()):
                return False
        else:
            positional += 1
            if positional > max_pos:
                return False
        i += 1
    return True


DENIED = "gh: read-only proxy denied this command or option; GitHub writes and bypass attempts are off-limits. Leave the action to the human.\n"


class Proxy:
    def __init__(self, path: Path, binary: str, root: Path):
        self.path, self.binary, self.root = path, binary, root.resolve()
        self.secrets = secret_values()
        owner = self

        class Handler(socketserver.StreamRequestHandler):
            def handle(self):
                self.connection.settimeout(5)
                try:
                    line = self.rfile.readline(LIMIT + 1)
                    if len(line) > LIMIT or not line.endswith(b"\n"):
                        raise ValueError("request too large or incomplete")
                    request = json.loads(line)
                    args = request.get("args")
                    if not allowed(args):
                        response = {"returncode": 1, "stdout": "", "stderr": DENIED}
                    else:
                        cwd = Path(request.get("cwd", str(owner.root))).resolve()
                        if not cwd.is_relative_to(owner.root) or not cwd.is_dir():
                            raise ValueError("repository context is outside workspace")
                        env = {k: os.environ[k] for k in ("HOME", "USER", "LANG", "GH_HOST", "GH_CONFIG_DIR", "XDG_CONFIG_HOME", *TOKEN_VARIABLES) if k in os.environ}
                        env.update(PATH="/usr/local/bin:/usr/bin:/bin", GH_PAGER="cat", PAGER="cat",
                                   GH_PROMPT_DISABLED="1", GH_NO_UPDATE_NOTIFIER="1")
                        # A temporary output file bounds in-memory reads even for large diffs.
                        import tempfile
                        with tempfile.TemporaryFile() as out, tempfile.TemporaryFile() as err:
                            result = subprocess.run([owner.binary, *args], cwd=cwd, env=env,
                                                    stdout=out, stderr=err, timeout=30)
                            out.seek(0); err.seek(0)
                            stdout, stderr = out.read(LIMIT + 1), err.read(LIMIT + 1)
                        if len(stdout) > LIMIT or len(stderr) > LIMIT:
                            raise ValueError("response exceeds 1 MiB; narrow the query")
                        response = {"returncode": result.returncode, "stdout": stdout.decode(errors="replace"), "stderr": stderr.decode(errors="replace")}
                except (ValueError, TypeError, AttributeError, OSError, subprocess.TimeoutExpired) as exc:
                    response = {"returncode": 1, "stdout": "", "stderr": f"gh proxy: {exc}\n"}
                try:
                    for key in ("stdout", "stderr"):
                        for secret in owner.secrets:
                            response[key] = response[key].replace(secret, "[REDACTED]")
                    self.wfile.write(json.dumps(response).encode() + b"\n")
                except OSError:
                    pass

        self.server = socketserver.UnixStreamServer(str(path), Handler)
        os.chmod(path, 0o600)
        self.thread = threading.Thread(target=self.server.serve_forever, kwargs={"poll_interval": 0.1}, daemon=True)
        self.thread.start()

    def close(self):
        self.server.shutdown()
        self.server.server_close()
        self.thread.join(timeout=2)
        self.path.unlink(missing_ok=True)


# Standalone standard-library adapter copied into a private sandbox PATH directory.
GH_ADAPTER = '''#!/usr/bin/env python3
import json, os, socket, sys
with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as sock:
    sock.settimeout(40)
    sock.connect(os.environ["SW_GH_SOCKET"])
    sock.sendall(json.dumps({"args": sys.argv[1:], "cwd": os.getcwd()}).encode() + b"\\n")
    stream = sock.makefile("rb")
    response = json.loads(stream.readline(3 * 1024 * 1024))
sys.stdout.write(response["stdout"])
sys.stderr.write(response["stderr"])
sys.exit(response["returncode"])
'''
