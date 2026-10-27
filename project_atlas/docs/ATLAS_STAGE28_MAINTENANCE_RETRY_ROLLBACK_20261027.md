# Stage 28 maintenance retry: FAIL, rollback verified

One owner-approved attempt used b88a56906b49dc07c5e05c1f60f793ab32ec7bdf.
The thermal correction passed. Installation failed postflight and was rolled back.
No automatic retry, bootloader operation, MCU read/write or movement occurred.

## Evidence

- Package SHA256: `12fbd59a38e2553e84474f5e2f889fb6a1f7467c5725947956fd38474b09f1cb`.
- Preflight CPU 58.2343%, RAM 60.6776%, maximum trustworthy temperature 59.906 C.
- Unavailable CV zones were classified not applicable, never as zero temperature.
- E-STOP latched, manual-only, commissioning disabled, STOPPED and zero commands.
- Original hashes and rollback archive verified before installation.
- Installed interlock module, recovery script and base service ExecCondition override; daemon-reload; restarted only sensor recovery.
- Postflight raised `AssertionError: E-STOP/zero/manual-only policy failure` at wrapper safety check. The rejected snapshot was not retained. The exact failing field and cause are unresolved; later safe samples do not explain the earlier failure.

## Verified rollback

Original recovery SHA256 restored:
`c6b5ac7979b6aff24c2f1a13a365d039b833da4c37997d3a8a07b21a928daaf5`.
New interlock module and service override removed. Inactive state moved into rollback evidence.
Only recovery restarted again for rollback; its log reports READY, full bounded fault recovery armed.

| Service | Before PID | After PID | NRestarts before/after |
|---|---:|---:|---|
| rover-base-telemetry | 3333 | 3333 | 1 / 1 |
| atlas-sensor-recovery | 1918 | 27172 | 0 / 0 |
| atlas-cmd-vel-mux | 1881 | 1881 | 0 / 0 |
| atlas-safety-status | 1910 | 1910 | 0 / 0 |
| atlas-camera | 1887 | 1887 | 0 / 0 |
| atlas-ekf | 3077 | 3077 | 0 / 0 |
| atlas-localization | 4686 | 4686 | 0 / 0 |
| atlas-lidar | 1882 | 1882 | 0 / 0 |
| atlas-voice-companion | 2090 | 2090 | 0 / 0 |
| rover-status-web | 2019 | 2019 | 0 / 0 |

All listed units active afterward. Two read-only post-rollback samples confirm latched stop, manual-only, zero commands and LIVE/READY telemetry. Encoder packets increased 74175 to 74200; packet age 0.02 to 0.04 seconds; checksum/write errors zero. Unrelated recovery was not deliberately fault-injected.

## Evidence and next gate

Jetson evidence and rollback:
`/home/jetson/project-atlas-migration/b1-maintenance-b88a569-20261027/`
(`result.json`, `resources.json`, `terminal.log`, `post-rollback.json`, `rollback/`).
Windows copy:
`C:/Users/Dhruv/Documents/Codex/2026-07-24/h/work/b1-maintenance-deploy-20261027/retry-b88a569/`.
Cross-host baseline archive SHA256:
`6f583eb097236eb675986d472b7ece3c74722a051f1867a58e0b98fed2bda87a`.
Raw logs/backups remain outside Git.

Maintenance deployment and B1 remain NO-GO. Next work is offline failure-diagnostic correction to retain the rejected safety snapshot and identify the failed predicate without weakening freshness or safety gates. A further deployment requires separate approval; B1 requires successful deployment and its own approval. This report does not authorize either operation.
