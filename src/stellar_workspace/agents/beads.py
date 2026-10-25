"""Canonical workspace tracker access; no implicit migration or Git operations."""
import json
import os
from pathlib import Path
import shutil
import subprocess

from ..workspace import WorkspaceError

PINNED_VERSION = '0.7.6'


def binary(root, config):
    requested = config.get('team', {}).get('br', 'programs/br/bin/br')
    path = Path(requested).expanduser()
    if not path.is_absolute():
        path = root / path
    found = str(path) if path.is_file() else (shutil.which(requested) if '/' not in requested else None)
    if not found and requested == 'programs/br/bin/br':
        found = shutil.which('br')
    if not found:
        raise WorkspaceError('beads-rust br is missing; run sw-agent install-br then sw-agent init-beads')
    return str(Path(found).resolve())


def run(root, config, args, *, actor=None, require=True):
    if require and not (root / '.beads').is_dir():
        raise WorkspaceError('Workspace tracker is missing; run sw-agent init-beads')
    if any(arg.split('=', 1)[0] == '--db' for arg in args):
        raise WorkspaceError('Use the canonical workspace tracker; --db routing overrides are not supported')
    if actor and any(arg.split('=', 1)[0] == '--actor' for arg in args):
        raise WorkspaceError('The managed agent actor cannot be overridden')
    env = {k: v for k, v in os.environ.items() if not k.startswith(('BD_', 'BR_', 'BEADS_'))}
    env.update(BEADS_DIR=str(root / '.beads'), NO_COLOR='1')
    command = [binary(root, config)]
    if actor:
        command += ['--actor', actor]
    result = subprocess.run([*command, *args], cwd=root, env=env, capture_output=True, text=True, timeout=30)
    if result.returncode:
        raise WorkspaceError(f"br failed ({result.returncode}): {result.stderr.strip() or result.stdout.strip()}")
    return result.stdout


def qualify(root, config):
    text = run(root, config, ['--version'], require=False).strip()
    fields = text.split()
    if len(fields) < 2 or fields[0] != 'br' or fields[1].removeprefix('v') != PINNED_VERSION:
        raise WorkspaceError(f'Expected qualified br {PINNED_VERSION}, found {text}; no migration was attempted')
    return text


def rows(text):
    value = json.loads(text)
    if isinstance(value, list):
        return value
    if isinstance(value, dict) and isinstance(value.get('issues'), list):
        return value['issues']
    if isinstance(value, dict) and 'id' in value:
        return [value]
    raise WorkspaceError('Unsupported br JSON response')


def ready(root, config, name):
    issues = rows(run(root, config, ['ready', '--assignee', name, '--json']))
    def permitted(issue):
        labels = issue.get('labels', [])
        return issue.get('assignee') == name and issue.get('status') == 'open' and not set(labels) & {'sw:awaiting-review', 'sw:needs-human', 'motd'}
    return sorted((i for i in issues if permitted(i)), key=lambda i: (i.get('priority', 4), i.get('created_at', ''), i['id']))


def show(root, config, identifier):
    values = rows(run(root, config, ['show', identifier, '--json']))
    if len(values) != 1:
        raise WorkspaceError('Expected one exact bead ID')
    return values[0]


def claim(root, config, name, identifier):
    issue = next((i for i in ready(root, config, name) if i['id'] == identifier), None)
    if not issue:
        raise WorkspaceError(f'{identifier} is not ready work assigned to {name}')
    if not issue.get('updated_at'):
        raise WorkspaceError('br omitted the revision guard; refusing an unguarded claim')
    return json.loads(run(root, config, ['update', identifier, '--claim', '--if-unchanged', issue['updated_at'], '--json'], actor=name))
