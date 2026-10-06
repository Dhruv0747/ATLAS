# Secure self-hosted runner: Phase 1/2

This branch intentionally contains only the repository-side entry point for a
read-only ATLAS health check. It does **not** contain deployment logic.

## Trust boundary

The workflow invokes a root-owned executable installed locally on the Jetson:

`/opt/atlas-ci/atlas-health-check`

The checked-out repository is not trusted to define the health-check logic.
The runner user must not be able to modify that executable or its fixed
service/topic allowlists.

The only permitted sudo rule for this phase should allow exactly the trusted
health-check command and no generic shell, systemctl, ROS publisher, or service
restart command.

## Safety

- Trigger: manual `workflow_dispatch` only.
- No push or pull-request trigger.
- No motion command.
- No navigation goal.
- No service restart.
- No deployment.
- Missing/stale safety data must be reported as unknown/fail by the trusted
  Jetson-side checker.

## Before merging to the default branch

1. Keep the repository private.
2. Protect `main` so agent-authored changes cannot bypass human review.
3. Protect `.github/workflows/**` with CODEOWNERS/review.
4. Verify the runner is repository-scoped and uses the dedicated
   `atlas-runner` Linux account.
5. Install and inspect the trusted root-owned checker under `/opt/atlas-ci`.
6. Add only the narrow sudoers entry required to run that exact checker.

Do not merge or run this workflow until the trusted local checker is installed.
