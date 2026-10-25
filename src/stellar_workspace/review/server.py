"""Loopback-only review server with pinned commits and authenticated mutations."""
from functools import partial
from http.server import BaseHTTPRequestHandler, HTTPServer
import json
import secrets
import sys
import webbrowser

from . import notes
from .generate import generate_html
from .git_ops import ReviewError

LIMIT = 200_000


class Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        if self.headers.get("Host") != self.server.authority:
            self.send_error(403)
            return
        if self.path in ("/", "/index.html"):
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Cache-Control", "no-store")
            self.send_header("X-Content-Type-Options", "nosniff")
            self.end_headers()
            self.wfile.write(self.server.html.encode())
        elif self.path == "/api/comments":
            try:
                self.respond(200, notes.read(self.server.repo, self.server.context["commit"])["records"])
            except ReviewError as exc:
                self.respond(500, {"error": str(exc)})
        else:
            self.send_error(404)

    def do_POST(self):
        if self.headers.get("Host") != self.server.authority or self.headers.get("Origin") != self.server.origin or not secrets.compare_digest(self.headers.get("X-SW-Token", ""), self.server.token):
            self.respond(403, {"error": "Invalid origin or mutation token"})
            return
        if self.headers.get_content_type() != "application/json":
            self.respond(400, {"error": "Expected application/json"})
            return
        try:
            length = int(self.headers.get("Content-Length", "0"))
            if not 0 < length <= LIMIT:
                raise ValueError("Invalid request size")
            body = json.loads(self.rfile.read(length))
            if not isinstance(body, dict):
                raise ValueError("Expected an object")
            repo, sha, who = self.server.repo, self.server.context["commit"], self.server.author
            if self.path in ("/api/comment", "/api/verdict"):
                result = notes.add(repo, sha, body, who, self.server.context, verdict=self.path == "/api/verdict")
            elif self.path in ("/api/resolve", "/api/unresolve"):
                identifier = body.get("id")
                if not isinstance(identifier, str):
                    raise ValueError("Missing comment id")
                result = notes.resolution(repo, sha, identifier, self.path == "/api/resolve", who)
            else:
                self.respond(404, {"error": "Unknown endpoint"})
                return
            self.respond(200, result)
        except (ReviewError, ValueError, TypeError, KeyError) as exc:
            self.respond(400, {"error": str(exc)})
        except OSError as exc:
            self.respond(500, {"error": str(exc)})

    def respond(self, status, data):
        payload = json.dumps(data).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(payload)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(payload)

    def log_message(self, *_):
        pass

    def setup(self):
        super().setup()
        self.connection.settimeout(10)


def make_server(repo, context, diffs, records, topic, base, commits, author, port=0):
    server = HTTPServer(("127.0.0.1", port), Handler)
    server.repo, server.context, server.author = repo, context, author
    server.authority = f"127.0.0.1:{server.server_address[1]}"
    server.origin = f"http://{server.authority}"
    server.token = secrets.token_urlsafe(32)
    server.html = generate_html(diffs, records, topic, base, commits, context, token=server.token)
    return server


def run_server(server, no_browser=False):
    print(server.origin + "/", flush=True)
    print("Review writes are pinned to " + server.context["commit"] + "; Ctrl-C to stop.", file=sys.stderr)
    try:
        if not no_browser:
            webbrowser.open(server.origin + "/")
        server.serve_forever(poll_interval=0.2)
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
