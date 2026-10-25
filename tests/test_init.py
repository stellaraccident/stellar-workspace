import json
import os
from pathlib import Path
import shutil
import subprocess
import sys

import pytest

from stellar_workspace.init import initialize, templates, digest, STATE
from stellar_workspace.workspace import WorkspaceError, load, discover, set_values


def test_primordial_no_site_packages(tmp_path):
    checkout = Path(__file__).resolve().parents[1]
    root = tmp_path / 'new workspace'
    result = subprocess.run(['python3', '-I', '-S', str(checkout / 'sw-init.py'), str(root)], cwd=tmp_path,
                            env={k:v for k,v in os.environ.items() if k not in {'PYTHONPATH', 'VIRTUAL_ENV'}}, capture_output=True, text=True)
    assert result.returncode == 0, result.stderr
    assert (root / 'AGENTS.md').is_file()
    assert not (root / '.venv').exists()
    assert not (root / '.git').exists()
    assert load(root)['sandbox']['gpu'] is True
    for name in ['add-repository', 'workspace-environment', 'sandbox-workflow', 'local-review']:
        assert (root / 'skills' / name / 'SKILL.md').is_file()
    assert not initialize(root)


def test_bootstrap_path_munging_uses_own_checkout(tmp_path):
    checkout = tmp_path / 'source space'
    checkout.mkdir()
    source = Path(__file__).resolve().parents[1]
    shutil.copy(source / 'sw-init.py', checkout)
    shutil.copytree(source / 'src', checkout / 'src')
    result = subprocess.run(['python3', '-I', '-S', str(checkout / 'sw-init.py'), str(tmp_path / 'new')], cwd='/', capture_output=True)
    assert result.returncode == 0, result.stderr


def test_dry_run_and_conflict_preflight(tmp_path):
    root = tmp_path / 'new'
    assert initialize(root, dry_run=True)
    assert not root.exists()
    root.mkdir()
    (root / 'README.md').write_text('custom')
    before = set(root.iterdir())
    with pytest.raises(WorkspaceError, match='initialized'):
        initialize(root, upgrade=True)
    assert set(root.iterdir()) == before
    initialize(root)
    assert (root / 'README.md').read_text() == 'custom'
    state = json.loads((root / STATE).read_text())
    assert 'README.md' not in state['files']


def test_upgrade_and_custom_conflicts(workspace):
    target = workspace / 'skills/local-review/SKILL.md'
    current = target.read_text()
    target.write_text('older generated skill\n')
    state_path = workspace / STATE
    state = json.loads(state_path.read_text())
    state['files']['skills/local-review/SKILL.md'] = digest(target.read_text())
    state_path.write_text(json.dumps(state))
    before = target.read_text()
    initialize(workspace, upgrade=True, dry_run=True)
    assert target.read_text() == before
    initialize(workspace, upgrade=True)
    assert target.read_text() == current
    assert list((workspace / '.tmp/sw-init-backups').glob('*/skills/local-review/SKILL.md'))
    target.write_text('local skill changes')
    with pytest.raises(WorkspaceError, match='Customized'):
        initialize(workspace, upgrade=True)
    assert target.read_text() == 'local skill changes'


def test_repair_deleted_marker_and_skills(workspace):
    (workspace / 'workspace.toml').unlink()
    (workspace / 'skills/local-review/SKILL.md').unlink()
    initialize(workspace, repair=True)
    assert load(workspace)['schema'] == 1
    assert (workspace / 'skills/local-review/SKILL.md').exists()
    assert (workspace / '.venv/bin/python').exists()


def test_config_edits_preserve_comments(workspace):
    path = workspace / 'workspace.toml'
    path.write_text(path.read_text().replace('gpu = false', 'gpu = false # keep comment') + '\n# local details\n')
    initialize(workspace, changes=[['sandbox.gpu', 'true'], ['sandbox.ro', '["/opt/sdk"]']])
    assert 'gpu = true # keep comment' in path.read_text()
    assert '# local details' in path.read_text()
    assert load(workspace)['sandbox']['ro'] == ['/opt/sdk']
    before = path.read_text()
    with pytest.raises(WorkspaceError):
        initialize(workspace, changes=[['sandbox.gpu', 'not-a-boolean']])
    assert path.read_text() == before


def test_symlink_escape_and_directory_conflicts(tmp_path):
    root = tmp_path / 'root'
    root.mkdir()
    outside = tmp_path / 'outside'
    outside.mkdir()
    (root / 'skills').symlink_to(outside, target_is_directory=True)
    with pytest.raises(WorkspaceError, match='symlink'):
        initialize(root)
    assert not list(outside.iterdir())


def test_discovery_and_schema(workspace, monkeypatch):
    monkeypatch.delenv('SW_WORKSPACE', raising=False)
    monkeypatch.chdir(workspace / 'docs')
    assert discover() == workspace
    monkeypatch.setenv('SW_WORKSPACE', str(workspace / 'missing'))
    with pytest.raises(WorkspaceError):
        discover()
    assert discover(workspace) == workspace
    config = workspace / 'workspace.toml'
    config.write_text(config.read_text().replace('schema = 1', 'schema = 200'))
    with pytest.raises(WorkspaceError, match='schema'):
        load(workspace)


def test_envrc_owns_venv_and_temp(workspace, tmp_path):
    parent = tmp_path / 'parent-venv'
    subprocess.run(['python3', '-m', 'venv', '--without-pip', str(parent)], check=True)
    # Stub direnv's shell API; run generated envrc without granting real trust.
    script = '''
source_up_if_exists() { export PARENT_SETTING=kept; }
PATH_add() { export PATH="$1:$PATH"; }
watch_file() { :; }
source "$VIRTUAL_ENV/bin/activate"
source .envrc
python -c 'import json,os,sys; print(json.dumps([sys.prefix,os.environ["TMPDIR"],os.environ["PARENT_SETTING"],os.environ["PATH"]]))'
'''
    env = {**os.environ, 'VIRTUAL_ENV': str(parent)}
    result = subprocess.run(['bash', '-c', script], cwd=workspace, env=env, capture_output=True, text=True)
    assert result.returncode == 0, result.stderr
    prefix, temp, parent_value, path = json.loads(result.stdout)
    assert prefix == str(workspace / '.venv')
    assert temp == str(workspace / '.tmp') and parent_value == 'kept'
    assert str(workspace / 'programs/bin') in path
    # Exercise first activation, starting from the parent venv.
    shutil.rmtree(workspace / '.venv')
    result = subprocess.run(['bash', '-c', script], cwd=workspace, env=env, capture_output=True, text=True)
    assert result.returncode == 0, result.stderr
    assert json.loads(result.stdout)[0] == str(workspace / '.venv')


def test_rename_updates_managed_guidance(workspace):
    initialize(workspace,changes=[['name','Renamed Workspace']])
    assert load(workspace)['name'] == 'Renamed Workspace'
    assert (workspace/'AGENTS.md').read_text().startswith('# Renamed Workspace')
    assert (workspace/'README.md').read_text().startswith('# Renamed Workspace')
    assert not initialize(workspace)


def test_directory_conflicts_preflight(tmp_path):
    root=tmp_path/'root'
    root.mkdir()
    (root/'programs').write_text('not a directory')
    with pytest.raises(WorkspaceError,match='directory'):
        initialize(root)
    assert not (root/'workspace.toml').exists()
