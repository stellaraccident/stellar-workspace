"""Dependency-free roster validation and managed team templates."""
from __future__ import annotations

from importlib.resources import files
from pathlib import Path
import re

from ..workspace import WorkspaceError

ROLES = {'lead', 'coder', 'reviewer', 'it'}
DEFAULT_ROSTER = {'lead': 'lead', 'ada': 'coder', 'grace': 'coder', 'lin': 'reviewer', 'it': 'it'}
NAME = re.compile(r'[a-z][a-z0-9_-]{0,31}')


def valid_name(name):
    if not isinstance(name, str) or not NAME.fullmatch(name):
        raise WorkspaceError('Agent names must be lowercase identifiers (1..32 characters)')
    return name


def validate_team(team):
    if not isinstance(team, dict) or team.keys() - {'shared_root', 'codex', 'br', 'poll_seconds', 'agents'}:
        raise WorkspaceError('Unknown or invalid team configuration')
    for key in ('shared_root', 'codex', 'br'):
        if key in team and (not isinstance(team[key], str) or not team[key].strip() or '\x00' in team[key]):
            raise WorkspaceError(f'team.{key} must be a nonempty path/string')
    if 'poll_seconds' in team and (type(team['poll_seconds']) not in (int, float) or not 1 <= team['poll_seconds'] <= 300):
        raise WorkspaceError('team.poll_seconds must be between 1 and 300')
    agents = team.get('agents', {})
    if not isinstance(agents, dict) or not agents:
        raise WorkspaceError('team.agents must define at least one named agent')
    for name, spec in agents.items():
        valid_name(name)
        if not isinstance(spec, dict) or spec.keys() - {'role', 'model', 'gpu', 'shared_ro', 'shared_rw'}:
            raise WorkspaceError(f'Unknown agent fields for {name}')
        if spec.get('role') not in ROLES:
            raise WorkspaceError(f'Agent {name} needs role lead, coder, reviewer or it')
        if 'model' in spec and (not isinstance(spec['model'], str) or not spec['model'].strip()):
            raise WorkspaceError(f'Invalid model for {name}')
        if 'gpu' in spec and type(spec['gpu']) is not bool:
            raise WorkspaceError(f'Invalid GPU flag for {name}')
        for key in ('shared_ro', 'shared_rw'):
            if key in spec and (not isinstance(spec[key], list) or any(not isinstance(p, str) or not p or Path(p).is_absolute() or '..' in Path(p).parts for p in spec[key])):
                raise WorkspaceError(f'{name}.{key} must contain paths below shared_root')
    return team


def team_text():
    text = '\n[team]\nshared_root = "~/agent-shared"\ncodex = "codex"\nbr = "programs/br/bin/br"\npoll_seconds = 5\n'
    for name, role in DEFAULT_ROSTER.items():
        text += f'\n[team.agents.{name}]\nrole = "{role}"\nshared_ro = []\nshared_rw = []\n'
    return text


def team_templates(team):
    resource = files('stellar_workspace').joinpath('resources')
    result = {'MOTD.md': '# Workspace notices\n\nNo active notices.\n'}
    for role in ROLES:
        result[f'agents/roles/{role}.md'] = resource.joinpath(f'role-{role}.md').read_text()
    for name, spec in team['agents'].items():
        result[f'agents/{name}/AGENTS.md'] = resource.joinpath('named-agent.md').read_text().replace('__AGENT__', name).replace('__ROLE__', spec['role'])
    for skill in ('team-operation', 'machine-operation'):
        result[f'skills/{skill}/SKILL.md'] = resource.joinpath('skills', skill, 'SKILL.md').read_text()
    result['agents/AGENTS.md'] = resource.joinpath('team-agents.md').read_text()
    return result
