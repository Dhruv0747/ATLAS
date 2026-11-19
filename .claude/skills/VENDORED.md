# Vendored skills: development environment only

Source: https://github.com/obra/superpowers, v7.0.1, commit 2ce8aa1 (2026-10-21), MIT licence (see SUPERPOWERS-LICENSE.txt). The files are unmodified upstream copies.

| Skill | Files |
|---|---|
| systematic-debugging | SKILL.md, root-cause-tracing.md, defense-in-depth.md, condition-based-waiting.md |
| test-driven-development | SKILL.md, writing-good-tests.md |
| requesting-code-review | SKILL.md, code-reviewer.md |
| using-git-worktrees | SKILL.md |
| writing-plans | SKILL.md |
| verification-before-completion | SKILL.md |

**ATLAS overrides:** `atlas-workflow/SKILL.md`. It wins over every vendored skill.

**Deliberately NOT installed:**
- The plugin's SessionStart hook and the `using-superpowers` skill. They force a skill call before every reply and brainstorming before planning.
- `brainstorming`, `subagent-driven-development`, `dispatching-parallel-agents`, `executing-plans`, `finishing-a-development-branch`, `writing-skills`, `diagnosing-superpowers`.

**Never deployed:** deploy packages archive only `project_atlas/`; `.claude/` lives at the repo root.

**Update:** copy the same files from a newer tag, update this file, then review the diff against `atlas-workflow`.
