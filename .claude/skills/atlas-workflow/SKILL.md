---
name: atlas-workflow
description: Use for any ATLAS code change, bug or review. ATLAS overrides for the vendored Superpowers skills (debugging, TDD, code review, worktrees, plans); these rules win wherever a vendored skill disagrees.
---

# ATLAS workflow (overrides the vendored Superpowers skills)

The vendored skills (`systematic-debugging`, `test-driven-development`, `requesting-code-review`, `using-git-worktrees`, `writing-plans`, `verification-before-completion`) come from obra/superpowers v7.0.1 (2ce8aa1, MIT). They are unmodified. Where they disagree with this file, **this file wins**. ATLAS safety rules always win over both.

## Never (safety; no skill can lift these)
- Do not deploy, restart services, release the E-STOP, command motors or flash firmware without the owner's explicit approval for that action.
- Do not weaken a safety gate or limit: the 75 % CPU / 80 % RAM / 70 °C limits, the 1.0 s observer freshness, the E-STOP priority, or driving caps.
- Repo-root `.claude/` is development-only. Deploy packages are `git archive HEAD project_atlas`, so nothing here reaches the Jetson. Keep it that way.

## Overrides
- **No automatic brainstorming.** Skip `brainstorming` and the "invoke a skill before ANY response" rule. Start from the owner's request. Ask one question only when a wrong guess is expensive.
- **TDD: never delete existing code.** "Write code before the test? Delete it" applies only to NEW code written in this session. ATLAS changes are additive with backups. Existing code gets a characterisation test first, then the change.
- **Risk-based testing (owner rule):**
  - Small isolated change: run the new tests and the affected suites only.
  - E-STOP, mux, motor-control or deployer-gate change: also the comprehensive safety suites (`test_stage29_deployer`, `test_stage29_reset_deployer`, `test_flysky_reset_offline`, mux tests).
  - Reuse green results when code and dependencies are unchanged. Run independent groups in parallel.
- **Code review:** for safety-critical changes use `requesting-code-review` (an independent reviewer). For small changes, a self-review against `requesting-code-review/code-reviewer.md` is enough.
- **Plans:** execute inline. `subagent-driven-development` and `executing-plans` are not vendored. No plan document for a change under about 100 lines.
- **Worktrees:** use the harness's native worktree tool, or `git worktree add` on a new `agent/...` branch. Never bare `git stash`. Commit as Dhruv0747 with the session trailers.
- **Physical results:** offline or simulated evidence is never reported as physical PASS. Lifted-wheel results are never reported as ground performance.
- **Reports:** a short PASS / FAIL / PENDING summary.
