# PR15 dual-client integration — 2026-10-31

## Implementation PASS

Six canonical Superpowers skills and the ATLAS override remain unchanged under
`.claude/skills`. Seven short `.agents/skills/*/SKILL.md` discovery manifests
reuse their metadata and link to those canonical instructions. Supporting
references resolve from the canonical directory. No duplicated instruction
bodies, full plugin, startup hooks or mandatory brainstorming were added.
Windows native symlink creation failed with WinError 1314; portable Markdown
reference manifests avoid administrator changes and checkout symlink privilege.
AGENTS.md and CLAUDE.md require reading ATLAS overrides before vendored skills.
Both skills trees stay outside the project_atlas-only deployment archive.

## Windows Codex Desktop PASS

A fresh local desktop chat was opened on this exact PR checkout using project
ATLAS PR15. Session 01a19028-e6a4-7531-b43a-4216d3e4af14 reported all six skills
in its actual available-skills metadata before file inspection:

- systematic-debugging
- test-driven-development
- requesting-code-review
- using-git-worktrees
- writing-plans
- verification-before-completion

It read all manifests and linked canonical instructions. A small practical
verification-before-completion exercise correctly rejected a claim that all
tests pass based only on yesterday's evidence after today's code changes, and
recommended only changed/affected tests under ATLAS risk-based testing. It
confirmed override precedence. No application code or physical tests ran.
Generic upstream subagent/workflow assumptions are subject to ATLAS overrides
and host tool availability; no full Superpowers runtime is implied.

## Claude Code PENDING: authentication

Installed Windows Claude Code 2.1.220 was invoked in this checkout for the same
read-only practical exercise, with only Read and Skill tools permitted. It
returned `Not logged in - Please run /login` before any model turn (zero API
inference). Thus filesystem compatibility passes but actual Claude discovery
and practical use are NOT verified. Owner must authenticate locally in Claude
Code; no credentials are requested or stored in repository/chat. Then repeat
only that small application smoke test, not the unrelated regression suites.

## Focused validation

Five discovery/scope tests PASS on WSL Ubuntu (0.44s). Canonical `.claude` diff
is empty. Reviewed project_atlas archive contains neither skill tree. Existing
19-test stop-analyzer/scope review evidence remains historical and is reused;
stop analyzer source was not changed. No Jetson access or service operation.

PR15 merge HOLD until the Claude practical check passes and owner approves.
PR13 description update deferred under the owner's sequential-completion rule.
