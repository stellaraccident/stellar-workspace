"""Known host GitHub and Python packaging credential sources.

No secret contents are included in plans or diagnostics. This is a deny policy
for machine auth state; user-selected workspace/data files must not contain secrets.
"""
from __future__ import annotations

import os
from pathlib import Path
import re
from urllib.parse import unquote, urlsplit

TOKEN_VARIABLES = ('GH_TOKEN', 'GITHUB_TOKEN', 'GH_ENTERPRISE_TOKEN', 'GITHUB_ENTERPRISE_TOKEN')
PACKAGING_PREFIXES = ('PIP_', 'TWINE_', 'UV_', 'PYPI_', 'POETRY_', 'FLIT_', 'PDM_PUBLISH_', 'HATCH_INDEX_', 'KEYRING_')


def credential_env(name: str) -> bool:
    return name in TOKEN_VARIABLES or name.startswith(PACKAGING_PREFIXES) or name in {
        'NETRC', 'PYTHON_KEYRING_BACKEND', 'DBUS_SESSION_BUS_ADDRESS', 'SSH_AUTH_SOCK', 'GPG_AGENT_INFO',
        'GH_CONFIG_DIR', 'GIT_CONFIG_GLOBAL', 'XDG_CONFIG_HOME', 'XDG_DATA_HOME', 'XDG_RUNTIME_DIR',
    }


def github_paths() -> list[Path]:
    home = Path.home()
    xdg = Path(os.environ.get('XDG_CONFIG_HOME', str(home / '.config')))
    return [Path(os.environ.get('GH_CONFIG_DIR', str(xdg / 'gh'))).expanduser().resolve(),
            (home / '.config/gh').resolve()]


def credential_paths(root: Path | None = None) -> list[Path]:
    home = Path.home()
    xdg = Path(os.environ.get('XDG_CONFIG_HOME', str(home / '.config')))
    data = Path(os.environ.get('XDG_DATA_HOME', str(home / '.local/share')))
    paths = [*github_paths(), home / '.gitconfig', home / '.git-credentials', xdg / 'git',
             home / '.netrc', home / '.authinfo', home / '.local/share/gh',
             home / '.pypirc', home / '.pip', xdg / 'pip', xdg / 'uv', xdg / 'pypoetry', xdg / 'pdm',
             xdg / 'python_keyring', data / 'python_keyring', data / 'keyrings',
             data / 'uv/credentials', data / 'pypoetry', Path('/etc/gitconfig'),
             Path('/etc/pip.conf'), Path('/etc/uv'), Path('/etc/xdg/pip'),
             Path('/etc/xdg/uv'), Path('/etc/xdg/python_keyring')]
    for entry in os.environ.get('XDG_CONFIG_DIRS', '/etc/xdg').split(':'):
        if entry:
            paths.extend(Path(entry) / name for name in ('pip', 'uv', 'python_keyring'))
    for name in ('GIT_CONFIG_GLOBAL', 'PIP_CONFIG_FILE', 'UV_CONFIG_FILE', 'TWINE_CONFIG_FILE', 'NETRC'):
        if os.environ.get(name) and os.environ[name] != os.devnull:
            paths.append(Path(os.environ[name]).expanduser())
    if os.environ.get('UV_STATE_DIR'):
        paths.append(Path(os.environ['UV_STATE_DIR']) / 'credentials')
    if os.environ.get('VIRTUAL_ENV'):
        paths.append(Path(os.environ['VIRTUAL_ENV']) / 'pip.conf')
    if root:
        paths.append(root / '.venv/pip.conf')
    return list(dict.fromkeys(path.resolve() for path in paths))


def secret_values() -> set[str]:
    values = {os.environ[key] for key in TOKEN_VARIABLES if os.environ.get(key)}
    url_pattern = r'https?://[^\s\"\'<>]+'
    def urls(text):
        for match in re.finditer(url_pattern, text):
            try:
                parsed = urlsplit(match[0])
                if parsed.password:
                    values.add(match[0])
                    values.add(unquote(parsed.password))
            except ValueError:
                pass
    for name, value in os.environ.items():
        if name.startswith(PACKAGING_PREFIXES):
            if any(part in name for part in ('TOKEN', 'PASSWORD', 'API_KEY')) and value:
                values.add(value)
            urls(value)
    for directory in github_paths():
        try:
            text = (directory / 'hosts.yml').read_text()
        except (OSError, UnicodeError):
            continue
        values.update(match[1] for match in re.finditer(r'(?m)^\s*oauth_token:\s*[\"\']?([^\s\"\']+)', text))
    paths = credential_paths()
    candidates = []
    for path in paths:
        if path.is_file():
            candidates.append(path)
        elif path.is_dir() and path.name in {'pip','uv','credentials','pypoetry','pdm'}:
            candidates.extend(path.glob('*.conf'))
            candidates.extend(path.glob('*.toml'))
    for path in candidates:
        try:
            if path.stat().st_size > 1024 * 1024:
                continue
            text = path.read_text()
        except (OSError, UnicodeError):
            continue
        values.update(re.findall(r'pypi-[A-Za-z0-9_-]+', text))
        values.update(match[1].strip().strip('\"\'') for match in re.finditer(r'(?mi)^\s*password\s*=\s*([^\n#]+)', text))
        urls(text)
    return {value for value in values if value}
