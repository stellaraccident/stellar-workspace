from pathlib import Path
import subprocess
import pytest

from stellar_workspace.init import initialize


@pytest.fixture
def workspace(tmp_path):
    root = tmp_path / 'space with spaces'
    initialize(root, source='/canonical/source')
    # Ordinary tests must also run on hosts without AMD GPU devices.
    initialize(root, changes=[['sandbox.gpu', 'false']])
    subprocess.run(['python3', '-m', 'venv', '--without-pip', str(root / '.venv')], check=True)
    return root


@pytest.fixture
def repo(tmp_path):
    root = tmp_path / 'repo'
    root.mkdir()
    def run(*args):
        return subprocess.run(['git', *args], cwd=root, check=True, capture_output=True)
    run('init', '-b', 'main')
    run('config', 'user.name', 'Repo Author')
    run('config', 'user.email', 'repo@example.org')
    (root / 'sample.py').write_text('print("before")\n')
    (root / 'deleted.txt').write_text('deleted\n')
    run('add', '.')
    run('commit', '-m', 'base')
    run('checkout', '-b', 'topic')
    (root / 'sample.py').write_text('print("after")\nsecond = 2\n')
    (root / 'new.txt').write_text('new\n')
    run('add', '.')
    run('commit', '-m', 'topic')
    return root
