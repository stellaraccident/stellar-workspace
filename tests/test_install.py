"""Offline distribution and force-reinstall tests in a clean target environment."""
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tarfile

import pygments
import pytest


@pytest.mark.packaging
def test_wheel_sdist_and_reinstall(tmp_path):
    source = Path(__file__).resolve().parents[1]
    checkout = tmp_path / 'canonical source'
    checkout.mkdir()
    for name in ('pyproject.toml', 'README.md', 'LICENSE', 'NOTICE', 'MANIFEST.in', 'sw-init.py'):
        shutil.copy2(source / name, checkout / name)
    shutil.copytree(source / 'src/stellar_workspace', checkout / 'src/stellar_workspace', ignore=shutil.ignore_patterns('__pycache__'))
    env = {k:v for k,v in os.environ.items() if k not in {'PYTHONPATH','VIRTUAL_ENV','SW_WORKSPACE'}}
    def run(args, cwd=tmp_path):
        result = subprocess.run(list(map(str,args)), cwd=cwd, env=env, capture_output=True, text=True)
        assert result.returncode == 0, result.stdout + result.stderr
        return result.stdout
    output = tmp_path / 'distributions'
    run([sys.executable,'-m','build','--no-isolation','--outdir',output,checkout])
    wheel = next(output.glob('*.whl'))
    sdist = next(output.glob('*.tar.gz'))
    with tarfile.open(sdist) as archive:
        assert any(name.endswith('/sw-init.py') for name in archive.getnames())
        unpack = tmp_path / 'sdist source'
        archive.extractall(unpack,filter='data')
    extracted = next(unpack.iterdir())
    run(['python3','-I','-S',extracted/'sw-init.py',tmp_path/'primordial'])
    target = tmp_path / 'installed'
    run(['python3','-m','venv',target])
    python = target / 'bin/python'
    run([python,'-m','pip','install','--no-index','--no-deps',wheel])
    site = Path(run([python,'-c','import sysconfig; print(sysconfig.get_path("purelib"))']).strip())
    # Provide the already-installed third-party renderer dependency offline.
    shutil.copytree(Path(pygments.__file__).parent,site/'pygments')
    guide = run([target/'bin/sw-agent-readme','--all'])
    assert 'Git notes review' in guide
    assert str(site) in run([python,'-I','-c','import stellar_workspace; print(stellar_workspace.__file__)'])
    root = tmp_path / 'created by installed command'
    run([target/'bin/sw-init',root])
    run([target/'bin/sw-init',root,'--repair'])
    for command in ('sw-init','sw-sandbox','sw-review','sw-agent-readme'):
        assert 'usage:' in run([target/'bin'/command,'--help'])
    # Installed renderer can create a snapshot without importing from checkout.
    from stellar_workspace.review.git_ops import git
    git(root,'init','-b','main')
    git(root,'config','user.name','Test')
    git(root,'config','user.email','test@example.org')
    git(root,'add','workspace.toml')
    git(root,'commit','-m','base')
    run([target/'bin/sw-review','-C',root,'open','HEAD','HEAD','--static',tmp_path/'review.html'])
    assert (tmp_path/'review.html').read_text().startswith('<!DOCTYPE html>')
    # Same-version source update and force-reinstall must replace resources.
    resource = checkout/'src/stellar_workspace/resources/agent-overview.md'
    resource.write_text(resource.read_text()+'\nREINSTALL_SENTINEL\n')
    run([sys.executable,'-m','build','--wheel','--no-isolation','--outdir',output,checkout])
    run([python,'-m','pip','install','--no-index','--no-deps','--force-reinstall',wheel])
    assert 'REINSTALL_SENTINEL' in run([target/'bin/sw-agent-readme'])
