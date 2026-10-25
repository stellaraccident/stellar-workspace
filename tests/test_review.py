from concurrent.futures import ThreadPoolExecutor
import http.client
import json
from pathlib import Path
import subprocess
import threading

import pytest

from stellar_workspace.review import git_ops as ops, notes
from stellar_workspace.review.cli import main
from stellar_workspace.review.generate import generate_html
from stellar_workspace.review.server import make_server


def commit(repo, message='change'):
    ops.git(repo, 'add', '.')
    ops.git(repo, 'commit', '-m', message)
    return ops.resolve(repo, 'HEAD')


def test_diff_and_log(repo):
    context = ops.comparison(repo, 'topic', 'main')
    files = ops.get_diff_files(repo, context['commit'], context['base'])
    assert {f.path for f in files} == {'sample.py', 'new.txt'}
    sample = next(f for f in files if f.path == 'sample.py')
    assert sample.additions == 2 and sample.deletions == 1
    assert ops.get_log(repo, context['commit'], context['base'])[0]['subject'] == 'topic'
    with pytest.raises(ops.ReviewError):
        ops.resolve(repo, '--help')


def test_diff_edge_cases(repo):
    (repo / 'deleted.txt').unlink()
    (repo / 'sample.py').rename(repo / 'renamed name\t"é.py')
    (repo / 'binary.bin').write_bytes(b'\0\xffbin')
    (repo / 'new.txt').write_text('no newline')
    (repo / 'mode.sh').write_text('#!/bin/sh\n')
    head = commit(repo)
    files = ops.get_diff_files(repo, head, ops.resolve(repo, 'topic~1'))
    assert any(f.path == 'deleted.txt' and f.status == 'D' and f.deletions == 1 for f in files)
    assert any(f.path == 'binary.bin' and f.binary for f in files)
    assert any(f.path == 'new.txt' and f.lines[-1].no_newline for f in files)
    assert any(f.path == 'renamed name\t"é.py' for f in files)
    # Isolate rename and mode-only comparisons against the current parent.
    (repo / 'mode.sh').chmod(0o755)
    (repo / 'new.txt').rename(repo / "renamed 'file'.txt")
    newhead = commit(repo)
    files = ops.get_diff_files(repo, newhead, head)
    assert any(f.status == 'R' and f.old_path == 'new.txt' for f in files)
    assert any(f.path == 'mode.sh' and not f.lines and 'mode' in f.metadata for f in files)


def test_comparison_modes_and_worktree(repo, tmp_path):
    ops.git(repo, 'checkout', 'main')
    (repo / 'base-only').write_text('base advanced')
    commit(repo)
    endpoint = ops.comparison(repo, 'topic', 'main')
    fork = ops.comparison(repo, 'topic', 'main', True)
    assert endpoint['base'] != fork['base']
    worktree = tmp_path / 'linked'
    ops.git(repo, 'worktree', 'add', str(worktree), 'topic')
    assert ops.find_repo(worktree) == worktree
    nested = worktree / 'nested'
    nested.mkdir()
    assert ops.find_repo(nested) == worktree
    assert ops.comparison(worktree, 'topic', 'main') == endpoint


def test_notes_round_trip_and_author(repo, monkeypatch):
    sha = ops.resolve(repo, 'topic')
    assert notes.read(repo, sha)['records'] == []
    monkeypatch.setenv('BR_ACTOR', 'ignored')
    monkeypatch.chdir('/')
    assert notes.author(repo) == 'Repo Author'
    record = notes.add(repo, sha, {'file':'sample.py','line':1,'body':'check'}, notes.author(repo))
    assert notes.resolution(repo, sha, record['id'], True, 'reviewer')['resolved']
    assert not notes.resolution(repo, sha, record['id'], False, 'reviewer')['resolved']
    notes.add(repo, sha, {'verdict':'request-changes','body':'fix'}, 'Reviewer', verdict=True)
    assert len(notes.read(repo, sha)['records']) == 2
    assert ops.git(repo, 'for-each-ref', '--format=%(refname)', 'refs/notes/sw-review-tmp/').stdout == b''
    monkeypatch.setenv('SW_REVIEW_AUTHOR','Env Author')
    assert notes.author(repo) == 'Env Author'
    assert notes.author(repo, 'Override') == 'Override'


def test_malformed_notes_never_overwritten(repo):
    sha = ops.resolve(repo, 'topic')
    ops.git(repo, 'notes','--ref',notes.REF,'add','-m','not json',sha)
    with pytest.raises(ops.ReviewError, match='Invalid review note'):
        notes.add(repo,sha,{'file':'a','line':1,'body':'text'},'a')
    assert ops.git(repo,'notes','--ref',notes.REF,'show',sha).stdout.strip() == b'not json'


def test_concurrent_writes_and_linked_worktree(repo, tmp_path):
    worktree = tmp_path / 'linked'
    ops.git(repo,'worktree','add','--detach',str(worktree),'topic')
    sha = ops.resolve(repo,'topic')
    def write(i):
        return notes.add(repo if i % 2 else worktree,sha,{'file':'a','line':i+1,'body':str(i)},'a')
    with ThreadPoolExecutor(max_workers=4) as pool:
        list(pool.map(write,range(12)))
    records = notes.read(repo,sha)['records']
    assert len(records) == 12
    assert {r['body'] for r in records} == set(map(str,range(12)))


@pytest.mark.parametrize('body', [
    {'file':'a','line':0,'body':'text'}, {'file':'a','line':True,'body':'text'},
    {'file':'../escape','line':1,'body':'text'}, {'file':'a','line':1,'body':''},
    {'file':'a','line':1,'body':'text','side':'unknown'},
])
def test_comment_validation(repo,body):
    with pytest.raises(ops.ReviewError):
        notes.add(repo,ops.resolve(repo,'topic'),body,'a')


def test_cli_json_and_errors(repo,capsys):
    assert main(['-C',str(repo),'add-comment','topic','--file','sample.py','--line','1','--body','hi']) == 0
    record = json.loads(capsys.readouterr().out)
    assert main(['-C',str(repo),'comments','topic','--unresolved']) == 0
    assert json.loads(capsys.readouterr().out)[0]['id'] == record['id']
    assert main(['-C',str(repo),'resolve','topic',record['id']]) == 0
    assert json.loads(capsys.readouterr().out)['resolved']
    assert main(['-C',str(repo),'show','topic']) == 0
    assert json.loads(capsys.readouterr().out)['schema'] == 1
    assert main(['-C',str(repo),'open','missing','main','--static',str(repo/'review.html')]) == 1
    assert 'fatal' in capsys.readouterr().err
    assert not (repo/'review.html').exists()


def test_render_and_static_escape(repo, tmp_path):
    # Git filenames may contain quotes, which must never enter inline handlers.
    path = "quote'\"<img>.txt"
    (repo / path).write_text('</script><img src=x onerror=alert(1)>\n')
    commit(repo)
    context = ops.comparison(repo,'topic','main')
    sha = context['commit']
    record = notes.add(repo,sha,{'file':path,'line':1,'body':'</script><img>'},'A<',context)
    files = ops.get_diff_files(repo,sha,context['base'])
    html = generate_html(files,[record],'topic','main',[],context)
    assert html.count('</script>') == 1
    assert '\\u003c/script\\u003e' in html
    assert 'innerHTML = line.html' in html
    assert 'READ-ONLY SNAPSHOT' in html
    output = tmp_path/'static.html'
    assert main(['-C',str(repo),'open','topic','main','--static',str(output)]) == 0
    assert output.read_text().startswith('<!DOCTYPE html>')


@pytest.fixture
def server(repo):
    context = ops.comparison(repo,'topic','main')
    files = ops.get_diff_files(repo,context['commit'],context['base'])
    try:
        server = make_server(repo,context,files,[],'topic','main',[],'Human')
    except PermissionError as exc:
        pytest.skip(f'Host forbids loopback sockets: {exc}')
    thread = threading.Thread(target=server.serve_forever,daemon=True)
    thread.start()
    yield server
    server.shutdown(); server.server_close(); thread.join(timeout=2)


def call(server,path,body=None,authorized=True):
    conn = http.client.HTTPConnection('127.0.0.1',server.server_address[1],timeout=5)
    headers = {'Content-Type':'application/json'}
    if authorized:
        headers.update(Origin=server.origin, **{'X-SW-Token':server.token})
    conn.request('POST' if body is not None else 'GET',path,body=json.dumps(body) if body is not None else None,headers=headers)
    response=conn.getresponse()
    payload=response.read()
    status=response.status
    conn.close()
    return status,payload


def test_http_round_trip_pins_commit(repo,server):
    old=server.context['commit']
    (repo/'advance').write_text('new')
    new=commit(repo)
    assert old != new
    status,payload=call(server,'/api/comment',{'file':'sample.py','line':1,'body':'check'})
    assert status == 200,payload
    record=json.loads(payload)
    assert notes.read(repo,new)['records'] == []
    assert notes.read(repo,old)['records'][0]['id'] == record['id']
    assert call(server,'/api/resolve',{'id':record['id']})[0] == 200
    assert call(server,'/api/unresolve',{'id':record['id']})[0] == 200
    assert call(server,'/api/verdict',{'verdict':'approve'})[0] == 200
    assert len(json.loads(call(server,'/api/comments')[1])) == 2
    assert call(server,'/api/comment',{'body':'incomplete'})[0] == 400
    assert call(server,'/api/comment',{'file':'a','line':1,'body':'blocked'},False)[0] == 403
    assert call(server,'/unknown')[0] == 404


@pytest.mark.integration
def test_browser_ui_smoke(server, tmp_path):
    """Exercise actual JavaScript rendering and mutations in an isolated browser."""
    import shutil
    chromium = shutil.which('chromium')
    if not chromium:
        pytest.skip('Chromium unavailable for browser smoke check')
    server.html += '''<script>
(async () => {
  try {
    if (!document.querySelector('table.code')) throw Error('Diff did not render');
    window.prompt = () => 'Browser feedback <img src=x onerror=alert(1)>';
    await addComment(DATA.files[0].path, 1, 'right');
    const comment = DATA.records.find(record => record.type === 'comment');
    if (!comment || document.querySelector('.comment-body img')) throw Error('Comment render/escape failed');
    await api('/api/resolve', {id:comment.id});
    if (!DATA.records.find(record => record.id === comment.id).resolved) throw Error('Resolve failed');
    await api('/api/unresolve', {id:comment.id});
    showVerdict('approve');
    document.getElementById('verdict-body').value = 'Browser verdict';
    await submitVerdict();
    if (!DATA.records.some(record => record.type === 'verdict')) throw Error('Verdict failed');
    document.body.dataset.smoke = 'passed';
  } catch (error) {
    document.body.dataset.smoke = error.stack;
  }
})();
</script>'''
    result = subprocess.run([chromium, '--headless', '--no-sandbox', '--disable-gpu',
                             '--disable-background-networking', '--no-proxy-server',
                             f'--user-data-dir={tmp_path / "browser-profile"}',
                             '--virtual-time-budget=10000', '--dump-dom', server.origin],
                            capture_output=True, text=True, timeout=40)
    assert result.returncode == 0, result.stderr
    assert 'data-smoke="passed"' in result.stdout, result.stdout[-5000:] + result.stderr[-1000:]
    records = notes.read(server.repo, server.context['commit'])['records']
    assert len(records) == 2
    assert records[0]['resolved'] is False and records[1]['verdict'] == 'approve'
