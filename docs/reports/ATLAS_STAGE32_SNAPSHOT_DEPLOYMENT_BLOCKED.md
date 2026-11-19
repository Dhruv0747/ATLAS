# Stage32 dashboard snapshot deployment: aborted before modification

2026-10-21. Owner approved single-file candidate27ed117 subject to fresh hash,
safety/resource and rollback checks. Exact live-file validation failed first.
No installation, backup replacement, restart, Astra Start, recording or movement
was performed. No rollback needed because production was not changed.

## Verified read-only evidence

Live `/home/jetson/project_atlas/scripts/atlas_status_web.py` SHA256:
`fa62787f94c63b0103c666855cef0175b2c86e40022bf700beebe77e44adbd12`.

Reviewed baseline Git LF SHA256:
`73094079d270ec146b442021da1996a0747554831c55a2ecaf342941f227fe78`.

Approved packaged candidate SHA256:
`e0b7d6eee33e02f889e22f60aee6b3f00ec636f39bfd2487f3d9d4d88ab6804c`.

Copied live source to local private evidence:
`artifacts/astra_concurrent_20261021/dashboard-predeploy-live.py`.
Line-normalized comparison proves substantive differences, not merely CRLF:
- Repository includes single-person steering service import, publishers, timer,
  cleanup and command action that live file does not include.
- Repository uses compact JSON; live uses indent=2.
- POST handler dispatch ordering differs.
- Commissioning request-size validation differs (additional8192-byte path in repo).

Deploying the entire approved repository file would therefore change more than
the two reviewed telemetry-bookkeeping operations. This is outside the narrow
change intent. Live differences must be preserved, not blindly overwritten.

Read-only systemctl: rover-status-web active, MainPID40386, NRestarts0.
Disk:368GiB available on467GiB filesystem (18% used).
These are not a complete safety or resource admission check.

## Measurements not performed

No matched CPU baseline/post comparison, temperature/RAM/sensor-freshness or
E-STOP admission claim: stopped at hash mismatch before those deployment steps.
No deployment backup created; older verified backups remain untouched.
No whole-Jetson CPU savings demonstrated. All production settings remain as found.

## Necessary next step

Prepare a live-baseline-derived single-file candidate applying ONLY the reviewed
_set deque-allocation and snapshot history-expiry changes. Re-run differential
tests using this exact live source as baseline and prove all unrelated AST nodes
are identical. Package exact hashes and a fresh backup/rollback procedure, then
request approval for the corrected package and rover-status-web-only restart.
Do not reuse approval to deploy unrelated repository additions.

The live pretty-printed JSON is a possible additional CPU cost, not measured
here and not authorization to alter serialization during this deployment.
No camera test should be retried on the basis of this aborted attempt.
