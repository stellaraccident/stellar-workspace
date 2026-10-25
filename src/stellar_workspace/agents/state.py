"""Small local state files, advisory locks and PID identity checks."""
from contextlib import contextmanager
import fcntl
import hashlib
import json
import os
from pathlib import Path
import tempfile
import time

from ..workspace import WorkspaceError
from ..init import contained
from .config import valid_name


def workspace_id(root):
    return hashlib.sha256(os.fsencode(root.resolve())).hexdigest()[:16]


def directory(root, name):
    return contained(root, f'.sw/agents/{valid_name(name)}')


def read(path, default=None):
    try:
        return json.loads(path.read_text())
    except FileNotFoundError:
        return {} if default is None else default
    except (ValueError, OSError) as exc:
        raise WorkspaceError(f'Cannot read state {path}: {exc}') from exc


def write(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary = tempfile.mkstemp(prefix='.state-', dir=path.parent)
    try:
        with os.fdopen(fd, 'w') as stream:
            json.dump(data, stream, indent=2)
            stream.write('\n')
        os.replace(temporary, path)
    finally:
        Path(temporary).unlink(missing_ok=True)


@contextmanager
def lock(path, *, blocking=True):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open('a+b') as handle:
        try:
            fcntl.flock(handle, fcntl.LOCK_EX | (0 if blocking else fcntl.LOCK_NB))
        except BlockingIOError as exc:
            raise WorkspaceError('This agent already has a running controller') from exc
        try:
            yield
        finally:
            fcntl.flock(handle, fcntl.LOCK_UN)


@contextmanager
def transaction(root, name):
    base = directory(root, name)
    with lock(base / 'state.lock'):
        value = read(base / 'state.json')
        yield value
        write(base / 'state.json', value)


def identity(pid):
    try:
        text = Path(f'/proc/{pid}/stat').read_text()
        fields = text[text.rfind(')') + 2:].split()
        if fields[0] == 'Z':
            return None
        return fields[19] # Linux starttime, field 22, after pid/comm.
    except (OSError, IndexError):
        return None


def alive(value):
    return bool(value.get('pid') and value.get('birth') and identity(value['pid']) == value['birth'])


def observed_alive(value):
    """Host PID identity, or a cooperative heartbeat view inside a PID namespace."""
    if os.environ.get('SW_SANDBOX') == '1':
        age = time.time() - value.get('heartbeat', 0)
        return bool(value.get('ready') and 0 <= age <= max(15, 3 * value.get('poll_seconds', 5)))
    return alive(value)
