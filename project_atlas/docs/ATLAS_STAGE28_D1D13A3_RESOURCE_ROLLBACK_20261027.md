# Stage 28 d1d13a3 maintenance attempt — resource rejection, rollback verified

2026-10-27: ONE explicitly authorized attempt, package SHA256 `0c8c940db0b143d9e81111bcc83b04e7877e4b9455ea87232b828a4ae120ca41`. Source d1d13a3612da69de82034d45359219ba038bf6d9; embedded runtime candidate remains 8736c73. All manifest hashes, original live baseline and independent rollback archive verified before writes.

## Result: FAIL / ROLLED_BACK

| Observation | CPU % | RAM % | Maximum C |
|---|---:|---:|---:|
| Preflight | 60.9215 | 60.7648 | 60.062 |
| Before writes | 62.0805 | 60.8329 | 60.062 |
| First post-restart resource sample | **98.8391** | 60.9149 | 60.343 |

CPU exceeded75%; RAM80% and temperature70C passed. Wrapper stopped and performed reviewed rollback. No threshold or freshness exception. Three atomic safety snapshots passed every predicate and their SHA256 integrity was independently rechecked after rollback. Unlike the previous attempt, this failure is demonstrably a CPU guard rejection, not a policy rejection. Attribution of the CPU spike to a particular process is not established; the earlier failed policy snapshot remains unavailable.

## Installed then restored

Temporarily installed the reviewed interlock module, recovery script and base ExecCondition override. User daemon-reload and recovery-only restart performed. Rollback restored original recovery SHA256 `c6b5ac7979b6aff24c2f1a13a365d039b833da4c37997d3a8a07b21a928daaf5`, removed interlock module/drop-in and restarted only recovery. Maintenance is not installed.

Base PID3333/NRestarts1 unchanged. Recovery PID27172 ->33128, active/NRestarts0 after rollback. Protected service PIDs unchanged and active: mux1881, safety1910, camera1887, EKF3077, localization4686, LiDAR1882, voice2090, web2019.

Two post-rollback observations: E-STOP true, manual-only true, commissioning false, source STOPPED; linear/angular commands zero. Telemetry LIVE, packets89715->89740, age0.014->0.042s. No base restart, camera start, movement, BOOT0/RESET, MCU read or firmware operation.

## Preserved evidence

Jetson directory: `/home/jetson/project-atlas-migration/b1-maintenance-d1d13a3-20261027/`; rollback in `rollback/`. Result, resources, terminal output and numbered safety snapshots preserved. Windows copy: `C:/Users/Dhruv/Documents/Codex/2026-07-24/h/work/b1-maintenance-deploy-20261027/retry-d1d13a3/`. Raw evidence remains outside Git.

Snapshot payload SHA256:
- safety-001: d4ebcf96e94943ae8ca3a825255f3430f080953a86ff4c8906c02c4be5bada02
- safety-002: 79f78a02d9aecf2459067b3d2ab66f34be4db4c4bde4d731ae552ced7e584608
- safety-003: 3d18b8b72b3319b2a92f49490b3239ea471018e80a301684add9535222616cbe

## Stop / next gate

No second attempt authorized or performed. Maintenance deployment and B1 remain NO-GO. Next work should investigate restart-time resource contention using retained evidence, without weakening75% CPU or retrying blindly. Any further deployment requires new explicit approval. B1 additionally requires successful maintenance verification and separate read-only backup approval.
