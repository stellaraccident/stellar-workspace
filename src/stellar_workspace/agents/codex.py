"""Codex's documented local control protocol; the native TUI remains the UI."""
from __future__ import annotations

from collections import deque
import json
from pathlib import Path
import socket
import time

from .. import __version__
from ..workspace import WorkspaceError


class Codex:
    def __init__(self, path: Path, timeout: float = 15):
        import websocket
        self.sequence = 0
        self.events = deque(maxlen=32)
        transport = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        transport.settimeout(timeout)
        try:
            transport.connect(str(path))
            self.ws = websocket.create_connection('ws://localhost/', socket=transport,
                                                  timeout=timeout, suppress_origin=True)
            self.call('initialize', {'clientInfo': {'name': 'stellar_workspace', 'version': __version__},
                                     'capabilities': {}})
            self.ws.send(json.dumps({'method': 'initialized', 'params': {}}))
        except Exception:
            transport.close()
            raise

    def call(self, method: str, params: dict | None = None):
        self.sequence += 1
        request = self.sequence
        self.ws.send(json.dumps({'id': request, 'method': method, 'params': params or {}}))
        deadline = time.monotonic() + 20
        while time.monotonic() < deadline:
            message = json.loads(self.ws.recv())
            if message.get('id') == request:
                if 'error' in message:
                    raise WorkspaceError(f"Codex {method}: {message['error'].get('message', message['error'])}")
                return message.get('result', {})
            if 'method' in message and 'id' not in message:
                self.events.append(message)
            elif 'method' in message and 'id' in message:
                # This connection is an observer/controller, never a host tool service.
                self.ws.send(json.dumps({'id': message['id'], 'error': {'code': -32601, 'message': 'Use the native interactive UI for approvals and questions'}}))
        raise WorkspaceError(f'Timed out waiting for Codex {method}')

    def close(self):
        self.ws.close()

    def __enter__(self):
        return self

    def __exit__(self, *_):
        self.close()
