"""Persistent sandboxed Codex backend, native TUI and small polling watcher."""
from __future__ import annotations

import hashlib
from importlib.resources import files
import json
import multiprocessing
import os
import re
from pathlib import Path
import shlex
import shutil
import signal
import subprocess
import sys
import tempfile
import time

from ..workspace import WorkspaceError, load
from ..init import contained
from ..sandbox.core import build_plan, execute
from ..sandbox.credentials import secret_values
from . import beads, state
from .codex import Codex


def roster(root, name):
    config = load(root)
    team = config.get('team')
    if not team:
        raise WorkspaceError('Team is not configured; run sw-init --team')
    if name not in team['agents']:
        raise WorkspaceError(f'Unknown agent {name}; configured: {", ".join(team["agents"])}')
    return config, team['agents'][name]


def shared_root(config):
    return Path(config['team'].get('shared_root', '~/agent-shared')).expanduser().resolve()


def machine_root(root):
    config = load(root)
    shared = shared_root(config)
    if not (shared / 'control/stellar-shared.json').is_file():
        raise WorkspaceError('Shared area is not initialized; run sw-agent init-shared explicitly')
    return shared / 'it'


def codex_binary(root, config):
    requested = config['team'].get('codex', 'codex')
    path = Path(requested).expanduser()
    if not path.is_absolute() and '/' in requested:
        path = root / path
    found = str(path.resolve()) if path.is_file() else shutil.which(requested)
    if not found:
        raise WorkspaceError('Codex CLI not found; configure team.codex with its executable path')
    return str(Path(found).resolve())


def tmux(*args, check=True):
    result = subprocess.run(['tmux', *args], capture_output=True, text=True, timeout=15)
    if check and result.returncode:
        raise WorkspaceError('tmux: ' + result.stderr.strip())
    return result


def session_name(root, name):
    return f'sw-{state.workspace_id(root)}-{name}'


def launcher(*args):
    return [sys.executable, '-m', 'stellar_workspace.agents.cli', *map(str, args)]


def notices(root, config):
    # File bind mounts can retain the old inode after an atomic host edit.
    # Managed clients read the controller's current notice snapshot instead.
    if os.environ.get('SW_SANDBOX') == '1' and os.environ.get('SW_AGENT'):
        snapshot = state.read(state.directory(root, os.environ['SW_AGENT']) / 'notices.json')
        if snapshot:
            return snapshot['revision'], snapshot['content']
    values = []
    shared = shared_root(config)
    if (shared / 'control/stellar-shared.json').is_file():
        paths = [('Machine', shared / 'MOTD.md')]
    else:
        paths = []
    paths.append(('Workspace', root / 'MOTD.md'))
    for title, path in paths:
        try:
            if path.stat().st_size > 64 * 1024:
                raise WorkspaceError(f'MOTD is too large: {path} (maximum 64 KiB)')
            text = path.read_text(encoding='utf-8')
        except FileNotFoundError:
            text = '(No notices file.)\n'
        if any(secret in text for secret in secret_values()):
            raise WorkspaceError(f'MOTD contains a host credential: {path}; refusing delivery')
        values.append(f'## {title}: {path}\n\n{text}')
    content = '\n\n'.join(values)
    revision = hashlib.sha256(content.encode()).hexdigest()
    return revision, f'Revision: {revision}\n\n{content}'


def host_socket(advertised):
    """Translate Codex's private /tmp rendezvous without exposing host daemons."""
    if not advertised.is_symlink():
        return advertised if advertised.exists() else None
    target = advertised.readlink()
    if target.parent != Path(f'/tmp/codex-daemon-{os.getuid()}') or not re.fullmatch(r'[0-9a-f]{64}', target.name):
        raise WorkspaceError('Unexpected Codex socket rendezvous target')
    physical = advertised.parent / 'daemon' / target.name
    if not physical.exists():
        return None
    endpoint = advertised.parent / 'host.sock'
    if not endpoint.is_symlink():
        endpoint.symlink_to(physical)
    return endpoint


def instructions(root, name, spec):
    resource = files('stellar_workspace').joinpath('resources')
    generic = resource.joinpath('agent-team.md').read_text()
    role = contained(root, f'agents/roles/{spec["role"]}.md').read_text()
    return generic + f'\nYour stable name is {name}; role is {spec["role"]}; workspace is {root}.\n' + role


def worker_plan(root, name, config, spec, runtime_dir):
    overrides = {'agent_profiles': ['codex']}
    if 'gpu' in spec:
        overrides['gpu'] = spec['gpu']
    plan = build_plan(root, config, overrides, agent_name=name)
    area = contained(root, f'agents/{name}')
    for child in ('tmp', 'build', 'cache', 'scratch', 'programs', 'logs', 'state'):
        contained(root, f'agents/{name}/{child}').mkdir(parents=True, exist_ok=True)
    plan.cwd = area
    # Keep credential hiding from the core plan; private /tmp goes before mounts
    # of workspaces that themselves live below /tmp.
    plan.mounts = [(flag, str(area / 'tmp'), target) if target == '/tmp' and flag == '--bind' else (flag, source, target)
                   for flag, source, target in plan.mounts]
    plan.mounts.append(('--bind', str(runtime_dir), str(runtime_dir)))
    daemon = runtime_dir / 'daemon'
    daemon.mkdir(mode=0o700, parents=True, exist_ok=True)
    plan.mounts.append(('--bind', str(daemon), f'/tmp/codex-daemon-{os.getuid()}'))
    binary = Path(codex_binary(root, config))
    if not binary.is_relative_to(Path('/usr')) and not binary.is_relative_to(root):
        plan.mounts.append(('--ro-bind', str(binary.parent), str(binary.parent)))
    plan.env.update(CODEX_HOME=str(area / 'state/codex'), SW_AGENT=name,
                    BEADS_DIR=str(root / '.beads'), SW_AGENT_SHARED=str(shared_root(config)),
                    XDG_CACHE_HOME=str(area / 'cache'))
    br = Path(beads.binary(root, config))
    if not br.is_relative_to(Path('/usr')) and not br.is_relative_to(root):
        plan.mounts.append(('--ro-bind', str(br), str(br)))
    # Workspace-local adapter gives interactive agents the canonical actor/db.
    adapter_dir = area / 'programs'
    adapter = adapter_dir / 'br'
    adapter.write_text(f'#!/bin/sh\nexec {shlex.quote(str(br))} --actor {shlex.quote(name)} "$@"\n')
    adapter.chmod(0o700)
    plan.env['PATH'] = f'{adapter_dir}:{binary.parent}:{plan.env["PATH"]}'
    shared = shared_root(config)
    if (shared / 'control/stellar-shared.json').is_file():
        # Read notices and coordination, not the whole global asset tree.
        plan.mounts.append(('--ro-bind', str(shared / 'MOTD.md'), str(shared / 'MOTD.md')))
        plan.mounts.append(('--ro-bind', str(shared / 'control'), str(shared / 'control')))
        for key, flag in (('shared_ro', '--ro-bind'), ('shared_rw', '--bind')):
            for relative in spec.get(key, []):
                target = (shared / relative).resolve()
                if not target.is_relative_to(shared) or not target.exists():
                    raise WorkspaceError(f'Invalid shared resource: {relative}')
                # Reuse the credential/overlap validation for explicit asset mounts.
                build_plan(root, config, {'agent_profiles': [], 'ro': [str(target)] if flag == '--ro-bind' else [],
                                         'rw': [str(target)] if flag == '--bind' else []})
                plan.mounts.append((flag, str(target), str(target)))
    return plan


def _backend(plan, command, log):
    with open(log, 'a', buffering=1) as output:
        os.dup2(output.fileno(), 1)
        os.dup2(output.fileno(), 2)
        raise SystemExit(execute(plan, command))


def queue(root, config, name, value, message):
    if not value.get('thread') or not value.get('socket'):
        raise WorkspaceError('Worker has no registered session')
    if any(secret in message for secret in secret_values()):
        raise WorkspaceError('Message contains a host credential; refusing delivery')
    # No host config, provider secrets or host daemon discovery for the frontend.
    env = frontend_env(root, name)
    result = subprocess.run([codex_binary(root, config), 'queue', '--remote', 'unix://' + value['socket'],
                             '--thread', value['thread'], '--message', message],
                            cwd=root / 'agents' / name, env=env, capture_output=True, text=True, timeout=20)
    if result.returncode:
        raise WorkspaceError('Codex queue failed: ' + result.stderr.strip())


def frontend_env(root, name):
    return {'PATH': '/usr/local/bin:/usr/bin:/bin', 'HOME': str(Path.home()),
            'CODEX_HOME': str(root / 'agents' / name / 'state/codex'),
            'TERM': os.environ.get('TERM', 'xterm-256color'), 'LANG': os.environ.get('LANG', 'C.UTF-8'),
            'SW_WORKSPACE': str(root), 'SW_AGENT': name}


def cycle(root, name, config, client):
    """One bounded poll; only changed notices/new assigned work invoke a model."""
    with state.transaction(root, name) as value:
        if value.get('stop'):
            return False
        thread = client.call('thread/read', {'threadId': value['thread']})['thread']
        value['client_status'] = thread.get('status', {}).get('type', 'unknown')
        value['heartbeat'] = time.time()
        if value.get('stop') or (value.get('stop_after_task') and value['client_status'] == 'idle'):
            return False
        revision, content = notices(root, config)
        state.write(state.directory(root, name) / 'notices.json', {'revision': revision, 'content': content})
        if revision != value.get('motd_revision'):
            queue(root, config, name, value, 'MOTD changed. Read and acknowledge these notices at your next safe checkpoint.\n' + content)
            value['motd_revision'] = revision
            value['motd_delivery'] = 'queued'
        if value.get('mode') != 'auto' or value['client_status'] != 'idle':
            return True
        if value.get('active_bead'):
            active = beads.show(root, config, value['active_bead'])
            if active.get('status') == 'in_progress':
                value['waiting_reason'] = 'Current bead needs a handoff/checkpoint before more pickup'
                return True
            value.pop('active_bead', None)
        issues = beads.ready(root, config, name)
        if not issues:
            value.pop('wake_key', None)
            return True
        fingerprint = hashlib.sha256(json.dumps([(i['id'], i.get('updated_at')) for i in issues]).encode()).hexdigest()
        if value.get('wake_key') == fingerprint:
            return True
        # Maintenance pauses all automatic pickup in this deliberately cooperative
        # MVP; CPU work remains available through a human-led session.
        maintenance = shared_root(config) / 'control/maintenance.json'
        if maintenance.is_file() and state.read(maintenance).get('active'):
            value['waiting_reason'] = 'Machine maintenance; automatic pickup paused'
            return True
        queue(root, config, name, value,
              f'Automatic queue wake for {name}. First run sw-agent status {name} and check MOTD. '
              'If your mode is not auto, wait for the human. Otherwise inspect your assigned ready beads, '
              'claim one conditionally using sw-agent claim, do the bounded work, record a handoff/checkpoint, '
              'then check for more assigned ready work before parking. Do not reclaim in-progress work.\n'
              + 'Ready IDs: ' + ', '.join(i['id'] for i in issues))
        value['wake_key'] = fingerprint
        value['last_wake'] = time.time()
        value.pop('waiting_reason', None)
    return True


def run(root, name):
    config, spec = roster(root, name)
    beads.qualify(root, config)
    if not (root / '.beads').is_dir():
        raise WorkspaceError('Tracker missing; run sw-agent init-beads')
    base = state.directory(root, name)
    with state.lock(base / 'run.lock', blocking=False), tempfile.TemporaryDirectory(prefix='sw-a-', dir='/tmp') as temp:
        runtime_dir = Path(temp)
        runtime_dir.chmod(0o700)
        sock = runtime_dir / 'codex.sock'
        plan = worker_plan(root, name, config, spec, runtime_dir)
        binary = codex_binary(root, config)
        command = [binary, 'app-server', '--listen', 'unix://' + str(sock)]
        process = multiprocessing.get_context('fork').Process(target=_backend, args=(plan, command, str(root / f'agents/{name}/logs/backend.log')))
        process.start()
        stopping = False
        def stop(*_):
            nonlocal stopping
            stopping = True
        previous = {sig: signal.signal(sig, stop) for sig in (signal.SIGTERM, signal.SIGINT, signal.SIGHUP)}
        try:
            deadline = time.monotonic() + 25
            while not host_socket(sock):
                if not process.is_alive() or time.monotonic() > deadline or stopping:
                    raise WorkspaceError(f'Codex backend did not start; inspect agents/{name}/logs/backend.log')
                time.sleep(.1)
            sock = host_socket(sock)
            with Codex(sock) as client:
                old = state.read(base / 'state.json')
                params = {'cwd': str(root / 'agents' / name), 'approvalPolicy': 'never',
                          'sandbox': 'danger-full-access', 'developerInstructions': instructions(root, name, spec)}
                if spec.get('model'):
                    params['model'] = spec['model']
                if old.get('thread'):
                    params.update(threadId=old['thread'], excludeTurns=True)
                    thread = client.call('thread/resume', params)['thread']['id']
                else:
                    thread = client.call('thread/start', params)['thread']['id']
                client.call('thread/name/set', {'threadId': thread, 'name': f'{config["name"]}/{name}'})
                revision, content = notices(root, config)
                state.write(base / 'notices.json', {'revision': revision, 'content': content})
                with state.transaction(root, name) as value:
                    value.update(pid=os.getpid(), birth=state.identity(os.getpid()), socket=str(sock), thread=thread,
                                 mode=('needs-human' if old.get('active_bead') else old.get('mode', 'human' if spec['role'] == 'lead' else 'auto')),
                                 stop=False, stop_after_task=False, ready=False, error=None, motd_revision=revision,
                                 client_status='idle', started=time.time(), workspace=str(root), name=name,
                                 poll_seconds=config['team'].get('poll_seconds', 5))
                    value.pop('wake_key', None)
                shared = shared_root(config)
                if (shared / 'control/stellar-shared.json').is_file():
                    state.write(shared / 'control/workspaces' / f'{state.workspace_id(root)}.json', {'workspace': str(root)})
                # Separate native UI window; it attaches to the same thread/backend.
                ui = launcher('--workspace', root, '_ui', name)
                tmux('new-window', '-d', '-t', session_name(root, name), '-n', 'ui', '-c', str(root), shlex.join(ui))
                tmux('set-window-option', '-t', session_name(root, name) + ':ui', 'remain-on-exit', 'on')
                with state.transaction(root, name) as value:
                    value['ready'] = True
                client.call('thread/unsubscribe', {'threadId': thread})
                while not stopping:
                    if not process.is_alive():
                        raise WorkspaceError('Sandboxed Codex backend exited; inspect backend.log')
                    try:
                        if not cycle(root, name, config, client):
                            break
                    except Exception as exc:
                        with state.transaction(root, name) as value:
                            value.update(error=str(exc), mode='needs-human')
                        print(f'Worker {name}: {exc}', flush=True)
                    time.sleep(config['team'].get('poll_seconds', 5))
        finally:
            process.terminate()
            process.join(timeout=5)
            if process.is_alive():
                process.kill()
                process.join()
            with state.transaction(root, name) as value:
                value.update(client_status='stopped', ready=False, stopped=time.time())
                value.pop('pid', None)
                value.pop('birth', None)
            for sig, handler in previous.items():
                signal.signal(sig, handler)


def start(root, name):
    if os.environ.get('SW_SANDBOX') == '1':
        raise WorkspaceError('Start persistent workers from the external operator shell; nested sandbox supervisors are unsupported')
    config, spec = roster(root, name)
    current = state.read(state.directory(root, name) / 'state.json')
    if state.alive(current):
        return current
    if not shutil.which('tmux'):
        raise WorkspaceError('tmux is required for persistent interactive workers')
    # Resolve dependencies before creating any terminal process.
    codex_binary(root, config)
    beads.qualify(root, config)
    if not (root / '.venv/bin/python').exists():
        raise WorkspaceError('Activate this workspace direnv venv and install stellar-workspace first')
    if not (root / '.beads').is_dir():
        raise WorkspaceError('Run sw-agent init-beads before starting a worker')
    session = session_name(root, name)
    if tmux('has-session', '-t', session, check=False).returncode == 0:
        raise WorkspaceError('A previous tmux session remains; inspect it before removing/restarting it: ' + session)
    command = launcher('--workspace', root, '_run', name)
    tmux('new-session', '-d', '-s', session, '-n', 'controller', '-c', str(root), shlex.join(command))
    deadline = time.monotonic() + 30
    while time.monotonic() < deadline:
        value = state.read(state.directory(root, name) / 'state.json')
        if state.alive(value) and value.get('ready') and value.get('socket') and Path(value['socket']).exists():
            return value
        if tmux('has-session', '-t', session, check=False).returncode:
            break
        time.sleep(.1)
    raise WorkspaceError('Worker did not become ready; inspect its tmux controller and backend.log')


def ui(root, name):
    config, _ = roster(root, name)
    value = state.read(state.directory(root, name) / 'state.json')
    if not state.alive(value):
        raise WorkspaceError('Worker is not running')
    command = [codex_binary(root, config), '--remote', 'unix://' + value['socket'],
               '--no-alt-screen', 'resume', value['thread']]
    os.chdir(root / 'agents' / name)
    os.execve(command[0], command, frontend_env(root, name))
