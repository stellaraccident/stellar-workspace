import pytest
from stellar_workspace.agent_readme import main, TOPICS


def test_installed_instruction_topics(capsys):
    assert main([]) == 0
    overview = capsys.readouterr().out
    for command in ('sw-init','sw-sandbox','sw-review','sw-agent-readme'):
        assert command in overview
    lengths = []
    for topic in TOPICS:
        assert main([topic]) == 0
        lengths.append(len(capsys.readouterr().out))
    assert main(['--all']) == 0
    assert len(capsys.readouterr().out) >= sum(lengths) + len(overview)
    with pytest.raises(SystemExit) as exc:
        main(['unknown'])
    assert exc.value.code == 2
