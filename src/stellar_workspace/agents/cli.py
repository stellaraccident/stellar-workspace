"""Operate persistent interactive Codex workers and their workspace bead queue."""
from __future__ import annotations

import argparse
import hashlib
import io
import json
import os
from pathlib import Path
import platform
import shutil
import subprocess
import sys
import tarfile
import urllib.request

from ..workspace import WorkspaceError, discover, load
from ..init import initialize, contained
from . import beads, runtime, state
from .config import valid_name


def install_br(root, *, dry_run=False):
    hashes = {
        'x86_64': ('amd64', '28b89f8f26540a4c9e6242b3c9fc93bcdd89f4ec0b9c9792895028c53f5bf2bd'),
        'aarch64': ('arm64', '7b6ea53d1b3b835115074e18bf6794caaf335bbe5b4f45fdb8091a9cf67c633a'),
    }
    if sys.platform != 'linux' or platform.machine() not in hashes:
        raise WorkspaceError('Automatic br installation supports Linux x86_64/aarch64; install br 0.7.6 manually elsewhere')
    arch, expected = hashes[platform.machine()]
    filename = f'br-{beads.PINNED_VERSION}-linux_musl_{arch}.tar.gz'
    url = f'https://github.com/Dicklesworthstone/beads_rust/releases/download/v{beads.PINNED_VERSION}/{filename}'
    destination = contained(root, 'programs/br/bin/br')
    if destination.exists():
        raise WorkspaceError(f'{destination} exists; inspect it instead of overwriting it')
    if dry_run:
        return {'download': url, 'sha256': expected, 'destination': str(destination)}
    with urllib.request.urlopen(url, timeout=60) as response:
        archive_bytes = response.read(100 * 1024 * 1024 + 1)
    if hashlib.sha256(archive_bytes).hexdigest() != expected:
        raise WorkspaceError('br release checksum mismatch; nothing was installed')
    with tarfile.open(fileobj=io.BytesIO(archive_bytes), mode='r:gz') as archive:
        matches = [member for member in archive.getmembers() if member.isfile() and Path(member.name).name == 'br']
        if len(matches) != 1 or matches[0].size > 150 * 1024 * 1024:
            raise WorkspaceError('Unexpected br release archive')
        binary = archive.extractfile(matches[0]).read()
    destination.parent.mkdir(parents=True, exist_ok=True)
    # Exclusive creation also protects a concurrent installer.
    with destination.open('xb') as stream:
        stream.write(binary)
    destination.chmod(0o755)
    return {'installed': str(destination), 'version': beads.PINNED_VERSION, 'archive_sha256': expected}


def init_shared(path, *, dry_run=False):
    path = path.expanduser().absolute()
    marker = path / 'control/stellar-shared.json'
    if path.is_symlink() or any(p.is_symlink() for p in path.parents):
        raise WorkspaceError('Shared area must not use a symlinked destination')
    if dry_run:
        return {'shared_root': str(path), 'directories': ['models', 'rocm', 'manifests', 'staging', 'control/workspaces', 'it'], 'writes': not marker.exists()}
    if marker.exists():
        return {'shared_root': str(path), 'status': 'already initialized'}
    # Refuse adopting arbitrary control state; never overwrite notices/metadata.
    for relative in ('control', 'it'):
        target = path / relative
        if target.exists() and (not target.is_dir() or any(target.iterdir())):
            raise WorkspaceError(f'Existing {target}; inspect before initializing shared state')
    for relative in ('models', 'rocm', 'manifests', 'staging', 'control/workspaces'):
        contained(path, relative).mkdir(parents=True, exist_ok=True)
    motd = contained(path, 'MOTD.md')
    if not motd.exists():
        motd.write_text('# Machine notices\n\nNo active maintenance.\n')
    initialize(path / 'it', name='Machine IT', team=True)
    config = path / 'it/workspace.toml'
    text = config.read_text().replace('shared_root = "~/agent-shared"', 'shared_root = ' + json.dumps(str(path)))
    before, it = text.split('[team.agents.it]', 1)
    it = it.replace('shared_rw = []', 'shared_rw = ["MOTD.md", "control", "models", "rocm", "manifests", "staging"]', 1)
    config.write_text(before + '[team.agents.it]' + it)
    state.write(marker, {'schema': 1, 'shared_root': str(path)})
    return {'shared_root': str(path), 'it_workspace': str(path / 'it'),
            'next': 'Activate/install the IT workspace venv, install br, initialize beads, then sw-agent start it --machine'}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--workspace')
    parser.add_argument('--machine', action='store_true', help='Target the shared IT workspace')
    sub = parser.add_subparsers(dest='command', required=True)
    for command in ('start', 'visit', 'auto', 'pause', 'stop', 'status', 'logs'):
        p = sub.add_parser(command)
        p.add_argument('name', nargs='?' if command == 'status' else None)
        if command == 'start':
            p.add_argument('--auto', action='store_true', help='Explicitly enable assigned-bead pickup for this run')
        if command == 'stop':
            p.add_argument('--after-task', action='store_true')
        if command == 'status':
            p.add_argument('--all-workspaces', action='store_true')
        if command == 'logs':
            p.add_argument('--follow', action='store_true')
    p = sub.add_parser('send')
    p.add_argument('name')
    p.add_argument('message')
    p = sub.add_parser('assign')
    p.add_argument('bead')
    p.add_argument('name')
    p = sub.add_parser('claim')
    p.add_argument('bead')
    p.add_argument('--name', help='Defaults to SW_AGENT in a managed worker')
    p = sub.add_parser('checkpoint')
    p.add_argument('--name')
    p.add_argument('--state', required=True, choices=['working', 'waiting', 'review', 'needs-human'])
    p.add_argument('--bead')
    p = sub.add_parser('beads', help='Run br against the canonical workspace tracker')
    p.add_argument('args', nargs=argparse.REMAINDER)
    p = sub.add_parser('install-br')
    p.add_argument('--dry-run', action='store_true')
    p = sub.add_parser('init-beads')
    p.add_argument('--dry-run', action='store_true')
    p = sub.add_parser('init-shared')
    p.add_argument('--path', type=Path, default=Path('~/agent-shared'))
    p.add_argument('--dry-run', action='store_true')
    sub.add_parser('doctor')
    p = sub.add_parser('motd')
    p.add_argument('action', nargs='?', choices=['show', 'status', 'ack'], default='show')
    p.add_argument('revision', nargs='?')
    p.add_argument('--all-workspaces', action='store_true')
    p = sub.add_parser('maintenance')
    p.add_argument('action', choices=['status', 'request', 'release'])
    p.add_argument('--reason')
    # Accept scope options on either side of a subcommand for operator comfort.
    for command_parser in sub.choices.values():
        command_parser.add_argument('--workspace', default=argparse.SUPPRESS)
        command_parser.add_argument('--machine', action='store_true', default=argparse.SUPPRESS)
    args = parser.parse_args(argv)
    try:
        if args.command == 'init-shared':
            result = init_shared(args.path, dry_run=args.dry_run)
            print(json.dumps(result, indent=2))
            return 0
        root = discover(args.workspace)
        if args.machine:
            root = runtime.machine_root(root)
        config = load(root)
        if 'team' not in config and args.command not in ('install-br', 'init-beads', 'beads'):
            raise WorkspaceError('Team is not configured; run sw-init --team')
        if args.command == 'install-br':
            result = install_br(root, dry_run=args.dry_run)
        elif args.command == 'init-beads':
            beads.qualify(root, config)
            if (root / '.beads').exists():
                raise WorkspaceError('Existing tracker preserved; no reinitialization or migration was attempted')
            if args.dry_run:
                result = {'initialize': str(root / '.beads'), 'version': beads.PINNED_VERSION}
            else:
                # br init itself creates its tracker; --force is never used.
                result = json.loads(beads.run(root, config, ['init', '--prefix', 'sw', '--json'], require=False))
        elif args.command == 'beads':
            command = args.args[1:] if args.args[:1] == ['--'] else args.args
            print(beads.run(root, config, command, actor=os.environ.get('SW_AGENT')), end='')
            return 0
        elif args.command == 'doctor':
            result = {'workspace': str(root), 'br': beads.qualify(root, config),
                      'codex': runtime.codex_binary(root, config), 'tracker': (root / '.beads').is_dir(),
                      'shared_initialized': (runtime.shared_root(config) / 'control/stellar-shared.json').is_file(),
                      'bubblewrap': shutil.which('bwrap')}
            probe = subprocess.run([result['codex'], 'queue', '--help'], capture_output=True, text=True, timeout=15)
            result['native_queue'] = probe.returncode == 0 and '--thread' in probe.stdout
        elif args.command in ('status', 'motd'):
            if args.command == 'motd' and args.action == 'show':
                print(runtime.notices(root, config)[1])
                return 0
            if args.command == 'motd' and args.action == 'ack':
                name = valid_name(os.environ.get('SW_AGENT', ''))
                runtime.roster(root, name)
                revision, _ = runtime.notices(root, config)
                if not args.revision or len(args.revision) < 12 or not revision.startswith(args.revision):
                    raise WorkspaceError('Acknowledge the current MOTD revision (at least 12 hash characters)')
                with state.transaction(root, name) as value:
                    value['motd_ack'] = revision
                result = {'agent': name, 'acknowledged': revision}
            else:
                roots = [root]
                if args.all_workspaces:
                    shared = runtime.shared_root(config)
                    roots += [Path(state.read(p)['workspace']) for p in (shared / 'control/workspaces').glob('*.json')]
                result = []
                for selected in dict.fromkeys(roots):
                    selected_config = load(selected)
                    names = [args.name] if args.command == 'status' and args.name else selected_config.get('team', {}).get('agents', {})
                    for name in names:
                        runtime.roster(selected, name)
                        value = state.read(state.directory(selected, name) / 'state.json')
                        result.append({'workspace': str(selected), 'name': name, **value, 'running': state.observed_alive(value)})
        elif args.command == 'maintenance':
            shared = runtime.shared_root(config)
            if not (shared / 'control/stellar-shared.json').exists():
                raise WorkspaceError('Shared area missing; run init-shared explicitly')
            path = shared / 'control/maintenance.json'
            if args.action == 'status':
                result = state.read(path, {'active': False})
            else:
                if not args.reason:
                    raise WorkspaceError('Maintenance changes require --reason')
                result = {'active': args.action == 'request', 'reason': args.reason, 'actor': os.environ.get('SW_AGENT', 'human')}
                state.write(path, result)
        elif args.command in ('assign', 'claim', 'checkpoint'):
            name = args.name or os.environ.get('SW_AGENT', '')
            runtime.roster(root, valid_name(name))
            if args.command == 'assign':
                issue = beads.show(root, config, args.bead)
                result = json.loads(beads.run(root, config, ['update', issue['id'], '--assignee', name,
                                                          '--if-unchanged', issue['updated_at'], '--json'], actor=os.environ.get('SW_AGENT', 'human')))
            elif args.command == 'claim':
                result = beads.claim(root, config, name, args.bead)
                with state.transaction(root, name) as value:
                    value.update(active_bead=args.bead, checkpoint='working')
            else:
                if args.bead:
                    issue = beads.show(root, config, args.bead)
                    if issue.get('assignee') != name:
                        raise WorkspaceError('Checkpoint bead belongs to another actor')
                with state.transaction(root, name) as value:
                    value['checkpoint'] = args.state
                    if args.state == 'needs-human':
                        value['mode'] = 'needs-human'
                    if args.state in ('waiting', 'review'):
                        value.pop('active_bead', None)
                    elif args.bead:
                        value['active_bead'] = args.bead
                    result = dict(value)
        else:
            name = valid_name(args.name)
            config, spec = runtime.roster(root, name)
            if spec['role'] == 'it' and not args.machine and root != runtime.shared_root(config) / 'it':
                raise WorkspaceError('IT is machine-wide; use sw-agent --machine start it')
            if args.command == 'start':
                return runtime.start(root, name, auto=args.auto)
            elif args.command == 'logs':
                path = contained(root, f'agents/{name}/logs/backend.log')
                if args.follow:
                    return subprocess.call(['tail', '-n', '50', '-f', str(path)])
                print(path.read_text()[-32_000:])
                return 0
            else:
                if args.command == 'visit':
                    runtime.require_terminal()
                with state.transaction(root, name) as value:
                    if not state.observed_alive(value):
                        raise WorkspaceError('Worker is not running; use sw-agent start ' + name)
                    if args.command in ('visit', 'pause'):
                        value['mode'] = 'human' if args.command == 'visit' else 'paused'
                    elif args.command == 'auto':
                        value['mode'] = 'auto'
                        value.pop('wake_key', None)
                    elif args.command == 'stop':
                        value['stop_after_task' if args.after_task else 'stop'] = True
                        value['mode'] = 'paused'
                    elif args.command == 'send':
                        runtime.queue(root, config, name, value, args.message)
                    result = dict(value)
                if args.command == 'visit':
                    return runtime.ui(root, name)
        print(json.dumps(result, indent=2))
        return 0
    except KeyboardInterrupt:
        return 130
    except (WorkspaceError, OSError, ValueError, subprocess.SubprocessError) as exc:
        print(f'sw-agent: {exc}', file=sys.stderr)
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
