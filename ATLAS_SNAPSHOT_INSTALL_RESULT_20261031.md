# Snapshot producer installation-only — PASS — 2026-10-31

One approved installation using b2519d5 exact-live package. Manifest SHA256:
c6b247d318e5b1abbc7d28e2b3dc746b2112692545903d3aa659e2eaa93d2ef5.
No retry, service restart/reload, production producer enablement, ROS/DDS node,
camera/inference, motion, firmware or control changes.

Preflight CPU61.6299%,RAM62.6269%,temp63.312C; postflightCPU63.5434%,RAM62.6977%,
temp63.25C. E-STOP latched, manual-only, zero commands, stationary encoders and LIVE
telemetry passed; packet ages0.028/0.040s. Astra OFF and empty process inventories;
legacy driver_stopped false retained separately rather than treated as authority.
These brief checks are not a resource-overhead benchmark.

Installed hashes:
- scripts/atlas_sensor_recovery.py:
  da83d138053a424d40fbff4a94532b864140953191260a32cc36042b5d51276a
- tools/vision3d/existing_safety_snapshot.py:
  e37cfd130c716f5bc014b91b6c7cd8c5ebdae85be916718cf07949d9f68f7c9c
- tools/vision3d/restart_safety_observer.py:
  a26b364f85df17e4fbbe05ff3174972b42180da3d0f44809cece967065dd47c1

Recovery PID2005 and Dashboard PID182915 healthy before installation. All atlas-*/
rover-* service state/PID/restart-count snapshots identical after installation.
Producer opt-in absent from systemd and process environment; snapshot file absent.
Current running recovery process retains original loaded code. Candidate will
remain output-disabled on future startup unless separately explicitly enabled.
No live producer lifecycle validation is claimed.

Evidence/backup:
/home/jetson/project-atlas-migration/snapshot-install-b2519d5/
result.json,services-before.txt,services-after.txt,original.py,reviewed manifest.
Original backup hash verified:
5f44cc1fbd7cdc65b8af17abeb9ecd41cec0a8c8f3ee8274fa9b34362633193a.
Rollback not needed. Exact rollback remains: verify candidate hashes/no concurrent
drift, atomically restore original.py as recovery script0644, verify originalhash,
then remove only the two verified newly-installed helper files. No service restart.

Next separately approved step: prepare a bounded producer runtime-validation
procedure with private runtime directory and explicit opt-in, exact configuration
backup/rollback, and at most one approved recovery-only restart. Verify actual
fresh callbacks, expiry behavior, resource overhead and independence from HTTP
without stopping Dashboard or protected telemetry. This installation does NOT
approve that restart/enablement or Object Detection backend activation.
