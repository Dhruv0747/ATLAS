"""Development skill packaging and ATLAS safety restrictions (no live operations)."""
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]

def test_skills_are_text_only_and_have_no_hooks():
    files = [p for p in (ROOT / '.claude').rglob('*') if p.is_file()]
    assert files
    assert all(p.suffix in ('.md', '.txt') for p in files)
    assert not any(p.name in ('hooks.json', 'settings.json') for p in files)
    assert not (ROOT / 'project_atlas/.claude').exists()

def test_atlas_overrides_preserve_owner_gates():
    text = (ROOT / '.claude/skills/atlas-workflow/SKILL.md').read_text()
    for required in ('explicit approval', '75 % CPU / 80 % RAM / 70', 'E-STOP priority',
                     '1.0 s observer freshness', 'never delete existing code',
                     'offline or simulated evidence is never reported as physical PASS'):
        assert required in text
    assert (ROOT / '.claude/skills/SUPERPOWERS-LICENSE.txt').is_file()

def test_only_reviewed_skills_vendored():
    actual = {p.parent.name for p in (ROOT / '.claude/skills').glob('*/SKILL.md')}
    assert actual == {'atlas-workflow', 'systematic-debugging', 'test-driven-development',
                      'requesting-code-review', 'using-git-worktrees', 'writing-plans',
                      'verification-before-completion'}


def test_codex_manifests_link_to_canonical_skills():
    import re
    canonical = {p.parent.name for p in (ROOT / '.claude/skills').glob('*/SKILL.md')}
    entries = list((ROOT / '.agents/skills').glob('*/SKILL.md'))
    assert {p.parent.name for p in entries} == canonical
    for entry in entries:
        text = entry.read_text(encoding='utf-8')
        source = ROOT / '.claude/skills' / entry.parent.name / 'SKILL.md'
        assert text.split('---')[1] == source.read_text(encoding='utf-8').split('---')[1]
        assert len(text.splitlines()) < 20
        for link in re.findall(r'\]\(([^)]+)\)', text):
            assert (entry.parent / link).resolve().is_file()
        assert 'atlas-workflow/SKILL.md' in text
    assert not (ROOT / 'project_atlas/.agents').exists()
    assert '.claude/skills/atlas-workflow/SKILL.md' in (ROOT/'AGENTS.md').read_text()


def test_both_clients_load_safety_overrides():
    for name in ('AGENTS.md', 'CLAUDE.md'):
        assert '.claude/skills/atlas-workflow/SKILL.md' in (ROOT/name).read_text()
    assert all(p.name == 'SKILL.md' for p in (ROOT/'.agents').rglob('*') if p.is_file())
