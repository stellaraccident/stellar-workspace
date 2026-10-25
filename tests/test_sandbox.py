import json
import os
from pathlib import Path
import signal
import socket
import subprocess
import threading

import pytest

from stellar_workspace.sandbox.core import LOCAL_TOOL_DIRECTORIES, build_plan, argv_for, execute
from stellar_workspace.sandbox.proxy import allowed, Proxy
from stellar_workspace.workspace import WorkspaceError, load


def test_plan_and_argv(workspace, monkeypatch):
    monkeypatch.setenv('VIRTUAL_ENV', '/other/venv')
    monkeypatch.setenv('SECRET_TOKEN', 'do-not-copy')
    plan = build_plan(workspace, load(workspace))
    assert plan.env['VIRTUAL_ENV'] == str(workspace / '.venv')
    assert 'SECRET_TOKEN' not in plan.env
    assert plan.env['TMPDIR'] == '/tmp'
    assert ('--bind', str(workspace), str(workspace)) in plan.mounts
    assert not plan.capabilities['gpu']
    handles = []
    try:
        argv = argv_for(plan, handles)
        assert '--clearenv' in argv
        assert '--unshare-pid' in argv
    finally:
        for h in handles: h.close()


def test_gpu_defaults_and_cli_override(workspace, monkeypatch, capsys):
    from stellar_workspace.sandbox.cli import main
    config = load(workspace)
    del config['sandbox']['gpu']
    exists = Path.exists
    monkeypatch.setattr(Path, 'exists', lambda path: path in (Path('/dev/kfd'), Path('/dev/dri')) or exists(path))
    plan = build_plan(workspace, config)
    assert plan.capabilities['gpu'] is True
    for device in ('/dev/kfd', '/dev/dri'):
        assert ('--dev-bind', device, device) in plan.mounts
    assert ('--ro-bind', '/sys', '/sys') in plan.mounts
    # Persisted configuration and CLI flags can still disable the default.
    assert not build_plan(workspace, load(workspace)).capabilities['gpu']
    path = workspace / 'workspace.toml'
    path.write_text(path.read_text().replace('gpu = false', 'gpu = true'))
    assert main(['--workspace', str(workspace), '--no-gpu', '--dry-run']) == 0
    assert not json.loads(capsys.readouterr().out)['capabilities']['gpu']


def test_reject_capability_and_mount_conflicts(workspace, tmp_path):
    config = load(workspace)
    with pytest.raises(WorkspaceError, match='incompatible'):
        build_plan(workspace, config, {'network':False, 'gh_proxy':True})
    for mount in ['/etc', '/tmp', str(workspace.parent), str(workspace / 'cache')]:
        with pytest.raises(WorkspaceError, match='protected'):
            build_plan(workspace, config, {'rw':[mount]})
    external = tmp_path / 'sdk'
    external.mkdir()
    plan = build_plan(workspace, config, {'ro':[str(external)]})
    assert ('--ro-bind', str(external), str(external)) in plan.mounts
    with pytest.raises(WorkspaceError, match='environment'):
        build_plan(workspace, config, {'env':{'PATH':'/bypass'}})


@pytest.fixture
def local_tools(tmp_path, monkeypatch):
    home = tmp_path / 'tool-home'
    for relative in LOCAL_TOOL_DIRECTORIES:
        (home / relative).mkdir(parents=True)
    release = home / '.codex/packages/standalone/releases/test/bin'
    release.mkdir(parents=True)
    binary = release / 'codex'
    binary.write_text('#!/bin/sh\nprintf "local codex help\\n"\n')
    binary.chmod(0o755)
    (home / '.codex/packages/standalone/current').symlink_to('releases/test')
    (home / '.local/bin/codex').symlink_to(home / '.codex/packages/standalone/current/bin/codex')
    (home / '.codex/config.toml').write_text('host configuration')
    (home / '.codex/auth.json').write_text('{"access_token":"fake-openai-credential"}')
    monkeypatch.setenv('HOME', str(home))
    return home


@pytest.mark.parametrize('profile', [None, 'codex'])
def test_local_tool_mounts_and_path(workspace, local_tools, profile):
    plan = build_plan(workspace, load(workspace), {'agent_profiles': [profile] if profile else []})
    for relative in LOCAL_TOOL_DIRECTORIES:
        path = str(local_tools / relative)
        assert ('--ro-bind', path, path) in plan.mounts
    path = plan.env['PATH'].split(':')
    assert path.index(str(workspace / '.venv/bin')) < path.index(str(local_tools / '.local/bin'))
    assert path.index(str(local_tools / '.local/bin')) < path.index('/usr/bin')
    assert not any(src == str(local_tools / '.local') for _, src, _ in plan.mounts)
    host_mount = ('--bind', str(local_tools / '.codex'), str(local_tools / '.codex'))
    assert (host_mount in plan.mounts) == (profile is None)
    if profile == 'codex':
        state_mount = next(i for i, (_, _, dst) in enumerate(plan.mounts) if dst == str(local_tools / '.codex'))
        package_mount = next(i for i, (_, _, dst) in enumerate(plan.mounts) if dst == str(local_tools / '.codex/packages'))
        assert state_mount < package_mount


def test_missing_or_symlinked_tool_directories_are_not_mounted(workspace, tmp_path, monkeypatch):
    home = tmp_path / 'empty-home'
    (home / '.local').mkdir(parents=True)
    (home / '.local/bin').symlink_to(tmp_path, target_is_directory=True)
    monkeypatch.setenv('HOME', str(home))
    plan = build_plan(workspace, load(workspace))
    assert not any(src == str(home / relative) for _, src, _ in plan.mounts for relative in LOCAL_TOOL_DIRECTORIES)
    assert not any(dst == str(home / '.codex') for _, _, dst in plan.mounts)


@pytest.mark.integration
@pytest.mark.parametrize('profile', [None, 'codex'])
def test_real_local_codex_available_read_only(workspace, local_tools, profile):
    import shutil
    if not shutil.which('bwrap'):
        pytest.skip('Bubblewrap is not installed')
    probe = subprocess.run(['bwrap', '--ro-bind', '/', '/', '--unshare-user', '--', 'true'], capture_output=True)
    if probe.returncode:
        pytest.skip('Host namespace policy prevents Bubblewrap: ' + probe.stderr.decode().strip())
    plan = build_plan(workspace, load(workspace), {'agent_profiles': [profile] if profile else []})
    script = '''
import errno, pathlib, subprocess
home = pathlib.Path.home()
assert subprocess.check_output(['codex', '--help'], text=True) == 'local codex help\\n'
assert (home / '.codex/config.toml').exists() == SHARED_HOST
assert (home / '.codex/auth.json').read_text() == '{"access_token":"fake-openai-credential"}'
(home / '.codex/session-probe').write_text('persisted session')
for relative in ('.local/bin/probe', '.codex/packages/probe'):
    try:
        (home / relative).write_text('must not write to host tools')
    except OSError as exc:
        assert exc.errno in (errno.EROFS, errno.EACCES), exc
    else:
        raise AssertionError('Host tool directory is writable')
'''
    script = 'SHARED_HOST = ' + repr(profile is None) + '\n' + script
    assert execute(plan, ['python', '-c', script]) == 0
    state = local_tools / '.codex' if profile is None else workspace / 'cache/agent-state/codex'
    assert (state / 'session-probe').read_text() == 'persisted session'
    assert (local_tools / '.codex/session-probe').exists() == (profile is None)


@pytest.mark.parametrize('args', [
    ['pr','list','-R','owner/repo','--state=open'], ['pr','view','12','--comments'],
    ['issue','list','--limit','5'], ['repo','view','owner/repo'], ['run','list'],
    ['search','code','a query','--owner','example'],
])
def test_proxy_reads_allowed(args):
    assert allowed(args)


@pytest.mark.parametrize('args', [
    ['pr','create'], ['pr','merge','1'], ['pr','review','1','--approve'], ['issue','comment','1'],
    ['api','repos/x/y','-XPOST'], ['api','repos/x/y','--method=POST'], ['api','x','-f','a=b'],
    ['api','graphql'], ['run','rerun','1'], ['run','download','1'], ['release','delete','v1'],
    ['auth','token'], ['pr','list','--web'], ['pr','list','--repo=--help'],
    ['pr','view','1','--template','x'], ['pr','view','1','--jq','.'],
    ['pr','list','--unknown'], ['pr','list','--state','--web'], ['pr','list','--state'],
    ['pr','list','--repo','x','--repo','y','extra'], ['pr','list','\n'], [], [1, 2],
])
def test_proxy_writes_and_unknown_options_denied(args):
    assert not allowed(args)


def request(path, body):
    with socket.socket(socket.AF_UNIX) as sock:
        sock.connect(str(path))
        sock.sendall(json.dumps(body).encode() + b'\n')
        return json.loads(sock.makefile('rb').readline())


def test_proxy_host_enforcement(workspace, tmp_path):
    binary = tmp_path / 'fake-gh'
    binary.write_text('#!/bin/sh\nprintf "read result"\n')
    binary.chmod(0o700)
    path = tmp_path / 'gh.sock'
    try:
        proxy = Proxy(path, str(binary), workspace)
    except PermissionError as exc:
        pytest.skip(f'Host forbids local sockets: {exc}')
    try:
        assert request(path, {'args':['pr','list']})['stdout'] == 'read result'
        denied = request(path, {'args':['pr','create']})
        assert denied['returncode'] == 1 and 'off-limits' in denied['stderr']
        assert request(path, {'args':['pr','list'], 'cwd':'/'})['returncode'] == 1
        assert request(path, {'args':None})['returncode'] == 1
    finally:
        proxy.close()
    assert not path.exists()


def test_execution_forwards_argv_status_cleanup(workspace, tmp_path, monkeypatch, capfd):
    # Replace Bubblewrap, not the command construction, to observe forwarding.
    binary = tmp_path / 'bwrap'
    binary.write_text('#!/usr/bin/python3\nimport json,sys\nprint(json.dumps(sys.argv[1:]))\nsys.exit(17)\n')
    binary.chmod(0o700)
    monkeypatch.setenv('PATH', f'{tmp_path}:{os.environ["PATH"]}')
    plan = build_plan(workspace, load(workspace))
    assert execute(plan, ['printf', 'literal $HOME', 'a b', '--flag']) == 17
    observed=json.loads(capfd.readouterr().out)
    assert observed[observed.index('--')+1:] == ['printf','literal $HOME','a b','--flag']
    assert not list((workspace / '.tmp').glob('sw-sandbox-*'))


@pytest.mark.integration
def test_real_bwrap_isolation(workspace):
    import shutil
    if not shutil.which('bwrap'):
        pytest.skip('Bubblewrap is not installed')
    probe = subprocess.run(['bwrap','--ro-bind','/','/','--unshare-user','--unshare-net','--','true'], capture_output=True)
    if probe.returncode:
        pytest.skip('Host namespace policy prevents Bubblewrap: ' + probe.stderr.decode().strip())
    plan = build_plan(workspace, load(workspace), {'network':False})
    script = 'import os,pathlib,socket; assert os.environ["TMPDIR"] == "/tmp"; pathlib.Path("/tmp/probe").write_text("ok"); assert not pathlib.Path.home().joinpath(".ssh/id_rsa").exists(); assert pathlib.Path("/etc/passwd").exists(); assert socket.if_nameindex() == [(1,"lo")]'
    assert execute(plan, ['python','-c',script]) == 0
    assert (workspace / '.tmp/probe').read_text() == 'ok'


def test_github_token_configuration_denied(workspace, monkeypatch, tmp_path):
    sentinel='github-env-token-sentinel'
    monkeypatch.setenv('GH_TOKEN', sentinel)
    for key,value in [('GH_TOKEN','value'),('GITHUB_TOKEN','value'),('GH_ENTERPRISE_TOKEN','value'),
                      ('GITHUB_ENTERPRISE_TOKEN','value'),('OTHER_SECRET',sentinel)]:
        with pytest.raises(WorkspaceError,match='environment'):
            build_plan(workspace,load(workspace),{'env':{key:value}})
    config=tmp_path/'host-gh-config'
    config.mkdir()
    (config/'hosts.yml').write_text('github.com:\n    oauth_token: github-file-token-sentinel\n')
    monkeypatch.setenv('GH_CONFIG_DIR',str(config))
    for mount in (config,config/'hosts.yml',config.parent):
        with pytest.raises(WorkspaceError,match='protected'):
            build_plan(workspace,load(workspace),{'ro':[str(mount)]})


@pytest.mark.integration
@pytest.mark.parametrize("profile_name", [None, "ada"])
@pytest.mark.parametrize("proxy_enabled,profile", [(False,None),(True,None),(True,"codex")])
def test_real_sandbox_cannot_read_github_tokens(workspace,tmp_path,monkeypatch,proxy_enabled,profile,profile_name):
    """Check protected credential files/environment and the gh proxy.

    Includes /proc environment inspection, custom GH_CONFIG_DIR, global Git
    config/credentials and the gh proxy. Explicit Codex profiles hide host
    config/snapshots; default host sharing intentionally exposes them.
    All credentials here are generated sentinels, never real user tokens.
    """
    import hashlib
    import shutil
    from stellar_workspace.sandbox import core
    if not shutil.which('bwrap'):
        pytest.skip('Bubblewrap unavailable')
    probe=subprocess.run(['bwrap','--ro-bind','/','/','--unshare-user','--unshare-net','--','true'],capture_output=True)
    if probe.returncode:
        pytest.skip('Host namespace policy prevents Bubblewrap: '+probe.stderr.decode())
    home=tmp_path/'host-home'
    (home/'.config/gh').mkdir(parents=True)
    (home/'.codex/shell_snapshots').mkdir(parents=True)
    (home/'.claude').mkdir()
    custom=tmp_path/'custom-gh'
    custom.mkdir()
    sentinels={key:f'sw-test-{key}-not-a-real-token' for key in
               ('GH_TOKEN','GITHUB_TOKEN','GH_ENTERPRISE_TOKEN','GITHUB_ENTERPRISE_TOKEN')}
    for key,value in sentinels.items():
        monkeypatch.setenv(key,value)
    file_token='sw-test-gh-file-not-a-real-token'
    git_token='sw-test-git-file-not-a-real-token'
    (custom/'hosts.yml').write_text(f'github.com:\n    oauth_token: {file_token}\n')
    (home/'.config/gh/hosts.yml').write_text(f'github.com:\n    oauth_token: {file_token}\n')
    (home/'.gitconfig').write_text(f'[http "https://github.com"]\n    extraheader = Authorization: bearer {git_token}\n')
    (home/'.git-credentials').write_text(f'https://x:{git_token}@github.com\n')
    (home/'.netrc').write_text(f'machine github.com password {git_token}\n')
    (home/'.codex/config.toml').write_text(f'[mcp_servers.github.env]\nGITHUB_TOKEN = "{sentinels["GH_TOKEN"]}"\n')
    (home/'.codex/shell_snapshots/leak.sh').write_text(f'export GH_TOKEN={sentinels["GH_TOKEN"]}\n')
    (home/'.claude/settings.json').write_text(json.dumps({'env':sentinels}))
    (home/'.claude.json').write_text(json.dumps({'env':sentinels}))
    (home/'.claude/.credentials.json').write_text('{"claudeAiOauth":{"accessToken":"fake-claude-credential"}}')
    (home/'.codex/auth.json').write_text('{"access_token":"fake-openai-credential"}')
    monkeypatch.setenv('HOME',str(home))
    monkeypatch.setenv('GH_CONFIG_DIR',str(custom))
    # Known token output must be redacted even if a host command prints it.
    binary=tmp_path/'fake-gh'
    binary.write_text('#!/usr/bin/python3\nimport os,pathlib\nassert os.environ["GH_TOKEN"].startswith("sw-test-")\nprint("host-authenticated",os.environ["GH_TOKEN"],pathlib.Path(os.environ["GH_CONFIG_DIR"],"hosts.yml").read_text())\n')
    binary.chmod(0o700)
    original=shutil.which
    monkeypatch.setattr(core.shutil,'which',lambda name,**kw: str(binary) if name=='gh' else original(name,**kw))
    tokens=[*sentinels.values(),file_token,git_token]
    hashes=[hashlib.sha256(token.encode()).hexdigest() for token in tokens]
    # Only hashes, never token literals, enter the child command line.
    script='''
import hashlib,json,os,pathlib,subprocess
hashes=set(json.loads(HASHES))
def check(data):
    # Tokens in this fixture contain no whitespace; also check embedded tokens.
    for token in data.replace(':',' ').replace('=',' ').replace('@',' ').replace('"',' ').split():
        assert hashlib.sha256(token.encode()).hexdigest() not in hashes, 'GitHub token exposed'
for key in ('GH_TOKEN','GITHUB_TOKEN','GH_ENTERPRISE_TOKEN','GITHUB_ENTERPRISE_TOKEN','GH_CONFIG_DIR'):
    assert key not in os.environ
for value in os.environ.values(): check(value)
for path in pathlib.Path('/proc').glob('[0-9]*/environ'):
    try: check(path.read_bytes().replace(b'\\x00',b' ').decode(errors='replace'))
    except (PermissionError,ProcessLookupError,FileNotFoundError): pass
for path in PATHS:
    candidate=pathlib.Path(path)
    if candidate.is_file():
        assert not candidate.read_bytes(), 'Host credential file exposed'
for relative in ('.codex/config.toml', '.codex/shell_snapshots/leak.sh'):
    candidate = pathlib.Path.home() / relative
    assert candidate.exists() == SHARED_CODEX
assert not pathlib.Path.home().joinpath('.claude/settings.json').exists()
assert not pathlib.Path.home().joinpath('.claude.json').exists()
if PROXY_ENABLED:
    result=subprocess.run(['gh','pr','list','-R','owner/repo'],capture_output=True,text=True)
    assert result.returncode==0, result.stderr
    assert 'host-authenticated' in result.stdout
    assert '[REDACTED]' in result.stdout
    check(result.stdout)
    for args in (['gh','auth','token'],['gh','api','user'],['gh','pr','create']):
        denied=subprocess.run(args,capture_output=True,text=True)
        assert denied.returncode != 0
        check(denied.stdout+denied.stderr)
'''
    paths=[str(custom/'hosts.yml'),str(home/'.config/gh/hosts.yml'),str(home/'.gitconfig'),str(home/'.git-credentials'),str(home/'.netrc')]
    script='SHARED_CODEX='+repr(profile is None)+'\nPROXY_ENABLED='+repr(proxy_enabled)+'\nHASHES='+repr(json.dumps(hashes))+'\nPATHS='+repr(paths)+'\n'+script
    plan=build_plan(workspace,load(workspace),{'gh_proxy':proxy_enabled,'agent_profiles':[profile] if profile else []}, agent_name=profile_name)
    assert execute(plan,['python','-c',script]) == 0
    assert not list((workspace/'.tmp').glob('sw-sandbox-*'))
    assert sentinels['GH_TOKEN'] not in json.dumps(plan.as_dict())


def test_pypi_config_and_alias_rejected(workspace,tmp_path,monkeypatch):
    home=tmp_path/'publishing-home'
    home.mkdir()
    token='pypi-FAKE-secret-for-test'
    (home/'.pypirc').write_text(f'[pypi]\nusername = __token__\npassword = {token}\n')
    monkeypatch.setenv('HOME',str(home))
    for key,value in [('TWINE_PASSWORD',token),('PYPI_TOKEN',token),('UV_PUBLISH_TOKEN',token),
                      ('POETRY_PYPI_TOKEN_PYPI',token),('PIP_INDEX_URL','https://x:y@example.org/simple'),
                      ('UV_INDEX_PRIVATE_PASSWORD',token),('OTHER_SETTING',token)]:
        with pytest.raises(WorkspaceError,match='environment'):
            build_plan(workspace,load(workspace),{'env':{key:value}})
    for mount in (home/'.pypirc',home):
        with pytest.raises(WorkspaceError,match='protected'):
            build_plan(workspace,load(workspace),{'ro':[str(mount)]})


@pytest.mark.integration
@pytest.mark.parametrize("named", [False, True])
def test_real_sandbox_cannot_read_pypi_credentials(workspace,tmp_path,monkeypatch,named):
    import hashlib
    import shutil
    if not shutil.which('bwrap'):
        pytest.skip('Bubblewrap unavailable')
    probe=subprocess.run(['bwrap','--ro-bind','/','/','--unshare-user','--unshare-net','--','true'],capture_output=True)
    if probe.returncode:
        pytest.skip('Host namespace policy prevents Bubblewrap: '+probe.stderr.decode())
    home=tmp_path/'publishing-home'
    home.mkdir()
    monkeypatch.setenv('HOME',str(home))
    env_tokens={'TWINE_PASSWORD':'pypi-FAKE-twine-env','PYPI_TOKEN':'pypi-FAKE-pypi-env',
                'UV_PUBLISH_TOKEN':'pypi-FAKE-uv-env','POETRY_PYPI_TOKEN_PYPI':'pypi-FAKE-poetry-env',
                'UV_INDEX_PRIVATE_PASSWORD':'pypi-FAKE-private-index'}
    for key,value in env_tokens.items(): monkeypatch.setenv(key,value)
    monkeypatch.setenv('PIP_INDEX_URL','https://__token__:pypi-FAKE-index@example.invalid/simple')
    monkeypatch.setenv('PIP_EXTRA_INDEX_URL','https://__token__:pypi-FAKE-extra@example.invalid/simple')
    config=tmp_path/'custom-pip.conf'
    config.write_text('[global]\nindex-url = https://x:pypi-FAKE-custom@example.invalid/simple\n')
    monkeypatch.setenv('PIP_CONFIG_FILE',str(config))
    files={home/'.pypirc':'[pypi]\nusername = __token__\npassword = pypi-FAKE-pypirc\n',
           home/'.config/pip/pip.conf':'[global]\nindex-url = https://x:pypi-FAKE-pip@example.invalid\n',
           home/'.pip/pip.conf':'[global]\nindex-url = https://x:pypi-FAKE-legacy@example.invalid\n',
           home/'.local/share/uv/credentials/credentials.toml':'password = "pypi-FAKE-uv-store"\n',
           home/'.local/share/python_keyring/keyring_pass.cfg':'pypi-FAKE-keyring',
           home/'.local/share/keyrings/login.keyring':'pypi-FAKE-system-keyring',
           home/'.config/pypoetry/auth.toml':'[pypi-token]\npypi = "pypi-FAKE-poetry"\n',
           home/'.netrc':'machine upload.pypi.org login __token__ password pypi-FAKE-netrc\n',
           workspace/'.venv/pip.conf':'[global]\nindex-url = https://x:pypi-FAKE-site@example.invalid\n'}
    for path,content in files.items():
        path.parent.mkdir(parents=True,exist_ok=True)
        path.write_text(content)
    for mount in (config,home/'.local/share/uv',home/'.local/share/python_keyring'):
        with pytest.raises(WorkspaceError,match='protected'):
            build_plan(workspace,load(workspace),{'ro':[str(mount)]})
    hashes=[hashlib.sha256(value.encode()).hexdigest() for value in env_tokens.values()]
    script='''
import hashlib,json,os,pathlib
hashes=set(HASHES)
for key in KEYS:
    assert key not in os.environ
assert os.environ['PIP_CONFIG_FILE']=='/dev/null'
assert os.environ['PIP_KEYRING_PROVIDER']=='disabled'
assert os.environ['UV_KEYRING_PROVIDER']=='disabled'
for value in os.environ.values():
    assert hashlib.sha256(value.encode()).hexdigest() not in hashes
for path in pathlib.Path('/proc').glob('[0-9]*/environ'):
    try:
        for field in path.read_bytes().split(b'\\x00'):
            value=field.partition(b'=')[2]
            assert hashlib.sha256(value).hexdigest() not in hashes
    except (PermissionError,ProcessLookupError,FileNotFoundError): pass
for name in FILES:
    path=pathlib.Path(name)
    if path.is_file(): assert not path.read_bytes(), 'Publishing credential file exposed'
'''
    keys=[*env_tokens,'PIP_INDEX_URL','PIP_EXTRA_INDEX_URL']
    script='HASHES='+repr(hashes)+'\nKEYS='+repr(keys)+'\nFILES='+repr(list(map(str,[*files,config])))+'\n'+script
    plan=build_plan(workspace,load(workspace),{'network':False,'agent_profiles':['codex'] if named else []}, agent_name='ada' if named else None)
    assert execute(plan,['python','-c',script]) == 0
    # Masking must not modify the real credential data in the workspace venv.
    assert 'pypi-FAKE-site' in (workspace/'.venv/pip.conf').read_text()


def test_signals_forwarded_and_runtime_cleaned(workspace,tmp_path,monkeypatch):
    import sys
    import time
    marker=tmp_path/'started'
    binary=tmp_path/'bwrap'
    binary.write_text('#!/usr/bin/python3\nimport pathlib,signal,sys,time\nsignal.signal(signal.SIGTERM, lambda *_: sys.exit(43))\npathlib.Path('+repr(str(marker))+').write_text("started")\nwhile True: time.sleep(.05)\n')
    binary.chmod(0o700)
    env={**os.environ,'PATH':f'{tmp_path}:{os.environ["PATH"]}'}
    source=str(Path(__file__).resolve().parents[1]/'src')
    env['PYTHONPATH']=source
    runner='from stellar_workspace.sandbox.cli import main; raise SystemExit(main())'
    process=subprocess.Popen([sys.executable,'-c',runner,'--workspace',str(workspace),'--','true'],env=env,stdout=subprocess.PIPE,stderr=subprocess.PIPE)
    try:
        deadline=time.monotonic()+5
        while not marker.exists() and process.poll() is None and time.monotonic()<deadline:
            time.sleep(.02)
        assert marker.exists()
        process.send_signal(signal.SIGTERM)
        stdout,stderr=process.communicate(timeout=5)
        assert process.returncode==43,stderr
    finally:
        if process.poll() is None:
            process.kill(); process.wait()
    assert not list((workspace/'.tmp').glob('sw-sandbox-*'))
