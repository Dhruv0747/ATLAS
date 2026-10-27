# Stage 28 postflight safety diagnostics — offline candidate

The failed b88a569 deployment reported in 9834093 cannot be retrospectively attributed to a particular condition. Its rejected API snapshot was discarded. Later safe telemetry establishes recovery, not the cause of that earlier rejection.

## Confirmed defect and correction

The wrapper previously asserted one boolean before saving any failing observation. It now evaluates and persists each condition before raising and before rollback:
- API response/JSON validity and observation presence/type.
- Policy and command ages: finite numeric, 0 through 1 second inclusive.
- E-STOP true, manual-only true, commissioning false, source STOPPED.
- Both linear and angular commands numeric zero (booleans rejected).

The unchanged original Interlock.safe predicate is still mandatory. Diagnostic disagreement also blocks admission. No missing/malformed/stale observation can become PASS. Original sample timestamps are preserved as evidence, not substituted for the existing age gate. Evaluation wall/monotonic times, fetch start/end, deployment stage, every failed predicate and reason are saved.

`safety_evidence.py` sanitizes the complete parsed snapshot recursively: credential-key values and arbitrary text are redacted; safe enumerations and numeric/boolean values remain visible. Non-finite numbers retain explicit invalid-number markers. Malformed strings retain length/hash where available, not potentially sensitive bodies. API errors retain exception type, not secret-bearing exception text. Raw HTTP bodies are intentionally not logged. Source timestamp trust is not newly asserted.

Each numbered snapshot is private, atomically replaced, file/directory fsynced on Linux, then read back and SHA256 verified. Rollback never removes snapshots. Persistence/integrity failure aborts admission and stores sanitized fallback evidence in the result and stderr before rollback. If storage AND terminal capture fail, durable evidence cannot be guaranteed; the system still denies admission. Hashes detect corruption, not malicious tampering.

## Offline validation

131 tests passed on PC Ubuntu 22.04 Python, covering wrapper transactions, interlock, readback, prompts, recovery isolation and new diagnostic tests. Includes released stop, wrong mode, commissioning, source, nonzero/invalid commands, stale/missing ages, API timeout, malformed JSON, simultaneous failures, atomic replace/fsync failures, checksum failure, exact freshness boundary, and full fake-service rollback with retained evidence after safety rejection or disk failure. No Jetson operations were performed.

## Candidate files and hashes (LF bytes)

- deploy_maintenance_once.py: `2f36fa7ee4b3d1490cc72fc611ba5b9cc85795f0c607b4dad256c6505b5a46c7`
- NEW sibling safety_evidence.py: `0eea20c5a9d30330331d0ed105305426edf59547fdae88197a2c86213104d51d`
- unchanged thermal helper: `1094daa20646255d5019d4354c848ea89dfc1f3a4c7663fc60fa9fd1549cf1c4`
- unchanged runtime candidate archive: `a28c5ea60de2b9276a2a275d1c2bb0bd303d959a61821b7f0217dc05a428a756`

Prepared local package: `C:/Users/Dhruv/Documents/Codex/2026-07-24/h/work/b1-maintenance-deploy-20261027/safety-diagnostics-retry-package.tar`.
Package SHA256: `0c8c940db0b143d9e81111bcc83b04e7877e4b9455ea87232b828a4ae120ca41`.
Archive member hashes re-read and verified offline. Include the new sibling helper when staging; do not reuse the old four-file package. Tests changed: test_b1_deployment_wrapper.py and new test_b1_safety_evidence.py. No production runtime/interlock/safety-policy changes.

## Verdict and approval

GO to request ONE maintenance-only retry approval, conditional on fresh safety/resources, original live hashes and rollback verification. NO-GO for execution under the current offline-only authorization. Existing CPU75/RAM80/TEMP70 and all safety gates remain unchanged. Use a new staging directory and preserve stdout/stderr, numbered snapshots and results outside the rollback directory. Keep the existing verified baseline archive and transactional rollback procedure. Restart only sensor recovery if separately approved; never base telemetry. No automatic retry.

The old postflight rejection may recur; the correction provides discriminating evidence, not a claimed fix of its unknown cause. B1, BOOT0, MCU reads/writes and movement remain unauthorized. Successful maintenance verification must precede a separate B1 approval.
