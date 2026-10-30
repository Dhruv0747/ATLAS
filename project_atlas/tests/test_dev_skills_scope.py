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
