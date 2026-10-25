from __future__ import annotations

from contextlib import contextmanager
import hashlib
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import os
from pathlib import Path
import pty
import select
import shutil
import subprocess
import sys
import threading
import time

import pytest

from stellar_workspace.init import initialize
from stellar_workspace.workspace import load, WorkspaceError
from stellar_workspace.agents import beads, state, runtime
from stellar_workspace.agents.cli import main
from stellar_workspace.agents.codex import Codex


@pytest.fixture
def team(workspace):
    initialize(workspace, team=True)
    return workspace


def test_team_setup_repeat_repair_and_protection(team):
    config=load(team)
    assert config['team']['agents']['lead']['role']=='lead'
    assert all('gpu' not in spec for spec in config['team']['agents'].values())
    assert (team/'agents/ada/AGENTS.md').is_file()
    assert '/.sw/agents/' in (team/'.gitignore').read_text()
    assert not initialize(team,team=True)
    (team/'agents/roles/coder.md').unlink()
    initialize(team,repair=True)
    assert (team/'agents/roles/coder.md').is_file()
    motd=team/'MOTD.md'
    motd.write_text('Human maintenance notice\n')
    with pytest.raises(WorkspaceError,match='Customized'):
        initialize(team,upgrade=True)
    assert motd.read_text()=='Human maintenance notice\n'


def test_primordial_team_without_site_packages(tmp_path):
    script=Path(__file__).resolve().parents[1]/'sw-init.py'
    result=subprocess.run(['python3','-I','-S',str(script),str(tmp_path/'new'),'--team'],capture_output=True)
    assert result.returncode==0,result.stderr
    assert (tmp_path/'new/agents/lead/AGENTS.md').exists()
    assert not (tmp_path/'new/.beads').exists()


@pytest.mark.parametrize('workspace_gpu,agent_gpu,expected', [
    (None, None, True), (True, None, True), (False, None, False),
    (True, False, False), (False, True, True),
])
def test_worker_gpu_inherits_workspace(team, tmp_path, monkeypatch, workspace_gpu, agent_gpu, expected):
    config = load(team)
    config['sandbox'].pop('gpu', None)
    if workspace_gpu is not None:
        config['sandbox']['gpu'] = workspace_gpu
    spec = config['team']['agents']['ada']
    if agent_gpu is not None:
        spec['gpu'] = agent_gpu
    home = tmp_path / 'worker-home'
    home.mkdir()
    monkeypatch.setenv('HOME', str(home))
    exists = Path.exists
    monkeypatch.setattr(Path, 'exists', lambda path: path in (Path('/dev/kfd'), Path('/dev/dri')) or exists(path))
    monkeypatch.setattr(runtime, 'codex_binary', lambda *args: '/usr/bin/true')
    monkeypatch.setattr(beads, 'binary', lambda *args: '/usr/bin/true')
    plan = runtime.worker_plan(team, 'ada', config, spec, tmp_path / 'runtime')
    assert plan.capabilities['gpu'] is expected
    assert (('--dev-bind', '/dev/kfd', '/dev/kfd') in plan.mounts) is expected


def test_shared_explicit_and_motd(team,tmp_path,capsys):
    shared=tmp_path/'shared'
    assert main(['init-shared','--path',str(shared),'--dry-run'])==0
    assert not shared.exists()
    assert main(['init-shared','--path',str(shared)])==0
    capsys.readouterr()
    config=team/'workspace.toml'
    config.write_text(config.read_text().replace('"~/agent-shared"',json.dumps(str(shared))))
    before=runtime.notices(team,load(team))[0]
    (shared/'MOTD.md').write_text('Global GPU maintenance\n')
    revision,text=runtime.notices(team,load(team))
    assert revision!=before and 'Global GPU maintenance' in text
    assert main(['--workspace',str(team),'maintenance','request','--reason','GPU checks'])==0
    assert state.read(shared/'control/maintenance.json')['active']
    assert main(['--workspace',str(team),'maintenance','release','--reason','Verified idle'])==0
    assert not state.read(shared/'control/maintenance.json')['active']
    assert main(['init-shared','--path',str(shared)])==0
    assert (shared/'MOTD.md').read_text()=='Global GPU maintenance\n'


def test_roster_validation_and_retired_claude(team):
    path=team/'workspace.toml'
    original=path.read_text()
    for invalid in ('poll_seconds = 0','poll_seconds = false'):
        path.write_text(original.replace('poll_seconds = 5',invalid))
        with pytest.raises(WorkspaceError): load(team)
    path.write_text(original.replace('agent_profiles = []','agent_profiles = ["claude"]'))
    with pytest.raises(WorkspaceError,match='retired'): load(team)


def test_state_lock_and_pid_identity(team):
    path=state.directory(team,'ada')/'run.lock'
    with state.lock(path):
        with pytest.raises(WorkspaceError,match='already'):
            with state.lock(path,blocking=False): pass
    assert state.alive({'pid':os.getpid(),'birth':state.identity(os.getpid())})
    assert not state.alive({'pid':os.getpid(),'birth':'not-the-same-process'})
    with pytest.raises(WorkspaceError): state.directory(team,'../escape')


class FakeControl:
    def __init__(self,status='idle'): self.status=status
    def call(self,method,params): return {'thread':{'status':{'type':self.status}}}


def setup_state(team,mode='auto'):
    state.write(state.directory(team,'ada')/'state.json',{'thread':'exact-uuid','socket':'/private/socket','mode':mode,
               'motd_revision':runtime.notices(team,load(team))[0], 'pid':os.getpid(),'birth':state.identity(os.getpid())})


def test_watcher_assigned_work_dedup_human_and_motd(team,monkeypatch):
    setup_state(team)
    sent=[]
    ready=[{'id':'sw-task','updated_at':'revision-one'}]
    monkeypatch.setattr(beads,'ready',lambda *args:ready)
    monkeypatch.setattr(runtime,'queue',lambda *args:sent.append(args[-1]))
    assert runtime.cycle(team,'ada',load(team),FakeControl())
    assert len(sent)==1 and 'sw-task' in sent[0]
    runtime.cycle(team,'ada',load(team),FakeControl())
    assert len(sent)==1 # No model-powered repeated wake.
    with state.transaction(team,'ada') as value: value['mode']='human'
    ready[0]['updated_at']='changed'
    runtime.cycle(team,'ada',load(team),FakeControl())
    assert len(sent)==1
    (team/'MOTD.md').write_text('Peer update\n')
    runtime.cycle(team,'ada',load(team),FakeControl('active'))
    assert len(sent)==2 and 'Peer update' in sent[-1]
    runtime.cycle(team,'ada',load(team),FakeControl('active'))
    assert len(sent)==2


def test_no_model_call_when_idle_or_maintenance(team,tmp_path,monkeypatch):
    setup_state(team)
    sent=[]
    monkeypatch.setattr(runtime,'queue',lambda *args:sent.append(args[-1]))
    monkeypatch.setattr(beads,'ready',lambda *args:[])
    runtime.cycle(team,'ada',load(team),FakeControl())
    assert not sent
    shared=tmp_path/'shared'
    (shared/'control').mkdir(parents=True)
    state.write(shared/'control/maintenance.json',{'active':True})
    config=load(team)
    config['team']['shared_root']=str(shared)
    monkeypatch.setattr(beads,'ready',lambda *args:[{'id':'sw-task','updated_at':'x'}])
    runtime.cycle(team,'ada',config,FakeControl())
    assert not sent
    assert 'maintenance' in state.read(state.directory(team,'ada')/'state.json')['waiting_reason']


def test_operator_visit_pauses_before_attach_and_auto_explicit(team,monkeypatch,capsys):
    setup_state(team)
    called=[]
    def attach(args):
        assert state.read(state.directory(team,'ada')/'state.json')['mode']=='human'
        called.append(args)
        return 0
    monkeypatch.setattr(subprocess,'call',attach)
    assert main(['--workspace',str(team),'visit','ada'])==0
    assert called and ':ui' in called[0][-1]
    assert state.read(state.directory(team,'ada')/'state.json')['mode']=='human'
    assert main(['--workspace',str(team),'auto','ada'])==0
    assert state.read(state.directory(team,'ada')/'state.json')['mode']=='auto'


def test_known_credentials_cannot_be_messages_or_motd(team,monkeypatch):
    monkeypatch.setenv('GH_TOKEN','fake-github-secret')
    (team/'MOTD.md').write_text('fake-github-secret')
    with pytest.raises(WorkspaceError,match='credential'): runtime.notices(team,load(team))
    monkeypatch.setenv('TWINE_PASSWORD','pypi-fake-test-secret')
    with pytest.raises(WorkspaceError,match='credential'):
        runtime.queue(team,load(team),'ada',{'thread':'uuid','socket':'/private'},'pypi-fake-test-secret')
    env=runtime.frontend_env(team,'ada')
    assert 'GH_TOKEN' not in env and 'TWINE_PASSWORD' not in env


@pytest.fixture
def real_br(team):
    requested=os.environ.get('SW_TEST_BR') or shutil.which('br')
    if not requested: pytest.skip('Set SW_TEST_BR to a qualified br 0.7.6 binary')
    config=load(team)
    config['team']['br']=str(Path(requested).resolve())
    beads.qualify(team,config)
    beads.run(team,config,['init','--prefix','test','--json'],require=False)
    return config


def test_real_beads_assigned_claim_and_guard(team,real_br):
    config=real_br
    issue=json.loads(beads.run(team,config,['create','Assigned work','--assignee','ada','--json']))
    beads.run(team,config,['create','Other work','--assignee','grace','--json'])
    assert [i['id'] for i in beads.ready(team,config,'ada')]==[issue['id']]
    beads.claim(team,config,'ada',issue['id'])
    assert not beads.ready(team,config,'ada')
    with pytest.raises(WorkspaceError,match='not ready'): beads.claim(team,config,'ada',issue['id'])
    assert beads.show(team,config,issue['id'])['status']=='in_progress'


@contextmanager
def fake_provider(tmp_path, delay_first=0):
    requests=[]
    class Handler(BaseHTTPRequestHandler):
        def do_POST(self):
            body=json.loads(self.rfile.read(int(self.headers['Content-Length'])))
            requests.append(body)
            text=f'Fixture response {len(requests)}'
            item={'id':'msg_fixture','type':'message','role':'assistant','status':'completed',
                  'content':[{'type':'output_text','text':text,'annotations':[]}]}
            response={'id':'resp_fixture','object':'response','created_at':1,'status':'completed',
                      'model':'fixture','output':[item],'usage':{'input_tokens':1,'output_tokens':1,'total_tokens':2}}
            events=[('response.created',{'response':{**response,'status':'in_progress','output':[]}}),
                    ('response.output_item.added',{'output_index':0,'item':{**item,'status':'in_progress','content':[]}}),
                    ('response.content_part.added',{'item_id':item['id'],'output_index':0,'content_index':0,'part':{'type':'output_text','text':'','annotations':[]}}),
                    ('response.output_text.delta',{'item_id':item['id'],'output_index':0,'content_index':0,'delta':text}),
                    ('response.output_text.done',{'item_id':item['id'],'output_index':0,'content_index':0,'text':text}),
                    ('response.output_item.done',{'output_index':0,'item':item}),
                    ('response.completed',{'response':response})]
            self.send_response(200)
            self.send_header('Content-Type','text/event-stream')
            self.end_headers()
            try:
                for kind,data in events:
                    self.wfile.write(('event: '+kind+'\ndata: '+json.dumps({'type':kind,**data})+'\n\n').encode())
                    self.wfile.flush()
                    if len(requests)==1 and kind=="response.created" and delay_first:
                        time.sleep(delay_first)
            except BrokenPipeError: pass
        def log_message(self,*_): pass
    server=ThreadingHTTPServer(('127.0.0.1',0),Handler)
    thread=threading.Thread(target=server.serve_forever,daemon=True)
    thread.start()
    try: yield server.server_address[1],requests
    finally: server.shutdown(); server.server_close(); thread.join(timeout=2)


def wait_for(check,timeout=20):
    deadline=time.monotonic()+timeout
    while time.monotonic()<deadline:
        value=check()
        if value: return value
        time.sleep(.05)
    raise AssertionError('Timed out waiting for native Codex integration')


@pytest.mark.integration
def test_native_codex_queue_tui_same_conversation(tmp_path):
    binary=os.environ.get('SW_TEST_CODEX') or shutil.which('codex')
    if not binary: pytest.skip('Codex CLI not installed')
    binary=str(Path(binary).resolve())
    home=tmp_path/'home'
    home.mkdir()
    codex_home=home/'codex'
    codex_home.mkdir()
    socket_path=Path('/tmp')/f'sw-test-codex-{os.getpid()}.sock'
    if socket_path.exists(): raise AssertionError('Unexpected preexisting test socket')
    env={'HOME':str(home),'CODEX_HOME':str(codex_home),'PATH':'/usr/bin:/bin','TERM':'xterm-256color','LANG':'C.UTF-8'}
    with fake_provider(tmp_path, delay_first=1.0) as (port,requests):
        (codex_home/'config.toml').write_text(f'model = "fixture"\nmodel_provider = "fixture"\n[model_providers.fixture]\nname = "fixture"\nbase_url = "http://127.0.0.1:{port}/v1"\nwire_api = "responses"\nrequires_openai_auth = false\nsupports_websockets = false\n')
        with (tmp_path/'server.log').open('w+') as log:
            backend=subprocess.Popen([binary,'app-server','--listen','unix://'+str(socket_path)],env=env,stdout=log,stderr=log)
            native=None
            master,slave=pty.openpty()
            import fcntl, termios, struct
            fcntl.ioctl(slave,termios.TIOCSWINSZ,struct.pack("HHHH",40,120,0,0))
            transcript=[]
            reading=True
            def reader():
                while reading:
                    if not select.select([master],[],[],.1)[0]: continue
                    try: data=os.read(master,65536)
                    except OSError: break
                    if not data: break
                    transcript.append(data)
                    if b'\x1b[6n' in data: os.write(master,b'\x1b[1;1R')
                    if b'\x1b[c' in data: os.write(master,b'\x1b[?1;2c')
            drain=threading.Thread(target=reader,daemon=True)
            drain.start()
            try:
                wait_for(socket_path.exists)
                with Codex(socket_path) as client:
                    result=client.call('thread/start',{'cwd':str(tmp_path),'approvalPolicy':'never','sandbox':'read-only'})
                    identifier=result['thread']['id']
                    client.call('thread/name/set',{'threadId':identifier,'name':'fixture-worker'})
                    native=subprocess.Popen([binary,'--remote','unix://'+str(socket_path),'--no-alt-screen','resume',identifier],
                                            env=env,stdin=slave,stdout=slave,stderr=slave,start_new_session=True)
                    wait_for(lambda:b'codex' in b''.join(transcript).lower())
                    first=subprocess.run([binary,'queue','--remote','unix://'+str(socket_path),'--thread',identifier,'--message','FIRST ASSIGNED TASK'],env=env,capture_output=True,text=True,timeout=15)
                    assert first.returncode==0,first.stderr
                    wait_for(lambda:len(requests)>=1)
                    wait_for(lambda:client.call('thread/read',{'threadId':identifier})['thread']['status']['type']=='active')
                    os.write(master,b'\x1b[200~HUMAN INTERACTIVE FOLLOWUP\x1b[201~')
                    time.sleep(.3) # Native paste handling must settle before Enter.
                    os.write(master,b'\r')
                    wait_for(lambda:len(requests)>=2)
                    wait_for(lambda:client.call('thread/read',{'threadId':identifier})['thread']['status']['type']=='idle')
                    wait_for(lambda:b'Fixture response 1' in b''.join(transcript))
                    again=subprocess.run([binary,'queue','--remote','unix://'+str(socket_path),'--thread',identifier,'--message','SECOND ASSIGNED TASK'],env=env,capture_output=True,text=True,timeout=15)
                    assert again.returncode==0,again.stderr
                    wait_for(lambda:len(requests)>=3)
                    wait_for(lambda:any('SECOND ASSIGNED TASK' in json.dumps(r) for r in requests))
                    combined=json.dumps([r for r in requests if r.get('tools')])
                    assert 'FIRST ASSIGNED TASK' in combined
                    assert 'HUMAN INTERACTIVE FOLLOWUP' in combined
                    assert 'SECOND ASSIGNED TASK' in combined
                    assert all(r.get('metadata',{}).get('thread_id',identifier)==identifier for r in requests if r.get('tools'))
            finally:
                (tmp_path/"native-transcript.bin").write_bytes(b"".join(transcript))
                reading=False
                if native:
                    native.terminate()
                    try: native.wait(timeout=5)
                    except subprocess.TimeoutExpired: native.kill(); native.wait()
                backend.terminate()
                try: backend.wait(timeout=5)
                except subprocess.TimeoutExpired: backend.kill(); backend.wait()
                os.close(slave); os.close(master)
                drain.join(timeout=2)
                socket_path.unlink(missing_ok=True)


@pytest.mark.integration
def test_persistent_tmux_worker_with_real_sandbox(team,real_br,tmp_path,monkeypatch):
    import tempfile
    binary=os.environ.get('SW_TEST_CODEX') or shutil.which('codex')
    if not binary or not shutil.which('tmux') or not shutil.which('bwrap'):
        pytest.skip('Codex, tmux and Bubblewrap are required')
    home=tmp_path/'host-home'
    home.mkdir()
    monkeypatch.setenv('HOME',str(home))
    # Never use a user's existing tmux server, configs, model endpoint or auth.
    with tempfile.TemporaryDirectory(prefix='sw-tm-',dir='/tmp') as tmux_temp, fake_provider(tmp_path) as (port,requests):
        monkeypatch.setenv('TMUX_TMPDIR',tmux_temp)
        monkeypatch.delenv('TMUX',raising=False)
        cfg=team/'workspace.toml'
        text=cfg.read_text().replace('codex = "codex"','codex = '+json.dumps(str(Path(binary).resolve())))
        text=text.replace('br = "programs/br/bin/br"','br = '+json.dumps(real_br['team']['br'])).replace('poll_seconds = 5','poll_seconds = 1')
        cfg.write_text(text)
        local=team/'agents/ada/state/codex'
        local.mkdir(parents=True)
        (local/'config.toml').write_text(f'model = "fixture"\nmodel_provider = "fixture"\n[model_providers.fixture]\nname = "fixture"\nbase_url = "http://127.0.0.1:{port}/v1"\nwire_api = "responses"\nrequires_openai_auth = false\nsupports_websockets = false\n')
        # Start without work: it must remain idle without model traffic.
        session=runtime.session_name(team,'ada')
        try:
            value=runtime.start(team,'ada')
            identifier=value['thread']
            assert state.alive(value)
            assert runtime.start(team,'ada')['thread']==identifier
            time.sleep(1.2)
            assert not requests
            first=json.loads(beads.run(team,load(team),['create','First assigned task','--assignee','ada','--json']))
            wait_for(lambda:any('Automatic queue wake' in json.dumps(r) for r in requests))
            # Native UI window renders the same response; no custom log UI.
            wait_for(lambda:'Fixture response' in runtime.tmux('capture-pane','-p','-S','-200','-t',session+':ui').stdout)
            with state.transaction(team,'ada') as current: current['mode']='human'
            beads.run(team,load(team),['close',first['id'],'--reason','fixture completed','--json'])
            second=json.loads(beads.run(team,load(team),['create','Second assigned task','--assignee','ada','--json']))
            count=len(requests)
            time.sleep(1.3)
            assert len(requests)==count
            with state.transaction(team,'ada') as current:
                current['mode']='auto'
                current.pop('wake_key',None)
            wait_for(lambda:any(second['id'] in json.dumps(r) for r in requests))
            latest=state.read(state.directory(team,'ada')/'state.json')
            assert latest['thread']==identifier
            (team/'MOTD.md').write_text('Maintenance fixture announcement\n')
            wait_for(lambda:any('Maintenance fixture announcement' in json.dumps(r) for r in requests))
            assert main(['--workspace',str(team),'stop','ada'])==0
            wait_for(lambda:not state.alive(state.read(state.directory(team,'ada')/'state.json')))
            wait_for(lambda:not Path(value['socket']).exists())
            wait_for(lambda:runtime.tmux('has-session','-t',session,check=False).returncode != 0)
            restarted=runtime.start(team,'ada')
            assert restarted['thread']==identifier
            assert restarted['mode']=='paused'
            assert main(['--workspace',str(team),'stop','ada'])==0
            wait_for(lambda:not state.alive(state.read(state.directory(team,'ada')/'state.json')))
        finally:
            # All terminal/backend processes belong to this private test server.
            runtime.tmux('kill-server',check=False)


@pytest.mark.integration
def test_named_worker_socket_mount_visible(team,real_br,tmp_path,monkeypatch):
    import tempfile
    from stellar_workspace.sandbox.core import execute
    binary=os.environ.get('SW_TEST_CODEX') or shutil.which('codex')
    if not binary or not shutil.which('bwrap'): pytest.skip('Codex and Bubblewrap required')
    home=tmp_path/'host-home'
    home.mkdir()
    monkeypatch.setenv('HOME',str(home))
    real_br['team']['codex']=str(Path(binary).resolve())
    with tempfile.TemporaryDirectory(prefix='sw-mount-',dir='/tmp') as directory:
        plan=runtime.worker_plan(team,'ada',real_br,real_br['team']['agents']['ada'],Path(directory))
        path=Path(directory)/'probe.sock'
        script='import socket; sock=socket.socket(socket.AF_UNIX); sock.bind('+repr(str(path))+'); sock.close()'
        assert execute(plan,['python','-c',script])==0
        assert path.exists()


@pytest.mark.integration
def test_sandboxed_codex_backend_listener(team,real_br,tmp_path,monkeypatch):
    import multiprocessing, tempfile
    binary=os.environ.get('SW_TEST_CODEX') or shutil.which('codex')
    if not binary or not shutil.which('bwrap'): pytest.skip('Codex/Bubblewrap required')
    home=tmp_path/'host-home'
    home.mkdir()
    monkeypatch.setenv('HOME',str(home))
    real_br['team']['codex']=str(Path(binary).resolve())
    with tempfile.TemporaryDirectory(prefix='sw-back-',dir='/tmp') as directory:
        plan=runtime.worker_plan(team,'ada',real_br,real_br['team']['agents']['ada'],Path(directory))
        plan.env['RUST_LOG']='codex_app_server=debug'
        path=Path(directory)/'codex.sock'
        log=tmp_path/'backend-diagnostic.log'
        proc=multiprocessing.get_context('fork').Process(target=runtime._backend,args=(plan,[str(Path(binary).resolve()),'app-server','--listen','unix://'+str(path)],str(log)))
        proc.start()
        try:
            endpoint=wait_for(lambda:runtime.host_socket(path),timeout=12)
            with Codex(endpoint) as client:
                assert 'thread' in client.call('thread/start',{'cwd':str(team/'agents/ada'),'approvalPolicy':'never','sandbox':'danger-full-access'})
        except Exception:
            print(log.read_text()[-5000:])
            raise
        finally:
            proc.terminate(); proc.join(timeout=5)
            if proc.is_alive(): proc.kill(); proc.join()


def test_canonical_tracker_and_actor_cannot_be_overridden(team):
    config=load(team)
    for args,actor in [(['--db=/other','list'],None), (['--db','/other','list'],None), (['--actor=other','list'],'ada')]:
        with pytest.raises(WorkspaceError,match='overrid'):
            beads.run(team,config,args,actor=actor,require=False)


def test_sandbox_notice_snapshot_survives_host_atomic_replacement(team,monkeypatch):
    setup_state(team)
    monkeypatch.setattr(beads,'ready',lambda *args:[])
    monkeypatch.setattr(runtime,'queue',lambda *args:None)
    replacement=team/'new-motd'
    replacement.write_text('Changed atomically')
    replacement.replace(team/'MOTD.md')
    runtime.cycle(team,'ada',load(team),FakeControl())
    expected=runtime.notices(team,load(team))
    # Simulate a file bind retaining its previous inode inside Bubblewrap.
    (team/'MOTD.md').write_text('Stale mounted notice')
    monkeypatch.setenv('SW_SANDBOX','1')
    monkeypatch.setenv('SW_AGENT','ada')
    assert runtime.notices(team,load(team))==expected


def test_sandbox_liveness_and_external_launch_boundary(team,monkeypatch):
    monkeypatch.setenv('SW_SANDBOX','1')
    assert state.observed_alive({'ready':True,'heartbeat':time.time(),'poll_seconds':5})
    assert not state.observed_alive({'ready':True,'heartbeat':time.time()-60,'poll_seconds':5})
    assert not state.observed_alive({'ready':False,'heartbeat':time.time()})
    with pytest.raises(WorkspaceError,match='external operator shell'):
        runtime.start(team,'ada')
