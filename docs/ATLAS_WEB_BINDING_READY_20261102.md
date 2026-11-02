# Bound Object/Target installation transaction — PREPARATION ONLY

Reuse c0e9a20 backend, inference disabled, existing guarded controller only.
Live execution NO-GO until existing Recovery producer supplies fresh validated
/run/user/1000/atlas-restart-safety/state.json independently of Dashboard HTTP.
No synthetic snapshot, extra ROS node or HTTP fallback is permitted.

Controller is control/web_activation_supervisor.py; REVIEW resolves its parent.
Four adjacent helpers are pinned, including the existing bounded_process_cpu.py.
20 payload manifest entries verified. Three replacements and seven additions only.
Seven focused binding tests PASS; packaged verifier PASS; independent review PASS.
The 21 backend tests are reused unchanged. Strict CPU<75,RAM<80,temp<70 retained.

Read-only current Consumer check: snapshot FileNotFoundError; Recovery PID2089,
NRestarts0, active, no ATLAS_RESTART_SNAPSHOT environment. Installed script SHA
 da83d138053a424d40fbff4a94532b864140953191260a32cc36042b5d51276a.
No service restart, producer enablement, camera, inference or latch reset occurred.

## Future staged paths, only after separate installation execution approval

Package root: /home/jetson/project-atlas-migration/vision-object-target-bound-20261102
Transaction evidence: /home/jetson/project-atlas-migration/web-activation-once-object-target-20261102
Verify archive SHA and BUNDLE_SHA256SUMS before execution. Never invoke the standalone
install_object_target_once.py: only the existing independent supervisor is permitted.

```sh
systemd-run --user --unit=atlas-web-object-target-once-20261102 --wait --collect --property=Type=exec --property=RuntimeMaxSec=180 --property=Restart=no --property=TimeoutStopSec=30 --property=KillMode=control-group '--property=ExecStopPost=/usr/bin/python3 -B /home/jetson/project-atlas-migration/vision-object-target-bound-20261102/control/web_activation_supervisor.py --stage /home/jetson/project-atlas-migration/web-activation-once-object-target-20261102 --recover' /usr/bin/python3 -B /home/jetson/project-atlas-migration/vision-object-target-bound-20261102/control/web_activation_supervisor.py --stage /home/jetson/project-atlas-migration/web-activation-once-object-target-20261102
```

NOTE: do NOT run this while snapshot is absent. The worker checks it before policy
or payload mutation. Python -I is not used for the main worker because the existing
control imports its sibling frozen modules; archive and all dependency hashes must
be verified first. The cleanup command likewise needs sibling import availability.

## Abort and rollback

One activation restart and at most one supervised rollback restart under existing
web-only Restart=no policy. Stop on any missing/stale safety snapshot, resource
failure, integrity drift or service mismatch. Exact originals retained under
package/rollback and LIVE_ROLLBACK_METADATA.json. Restore the three originals;
remove only matching seven additions, refusing unexpected later edits. Recovery,
ROS, camera, monitoring and mapping files are not targets. Runtime checks preserve
all protected identities. ExecStopPost runs existing --recover cleanup; if unsafe,
web stays stopped and manual recovery is reported, never repeated automatically.
No camera start, recording or inference is enabled by installation.

Private PC archive: C:\Users\Dhruv\Documents\Codex\2026-07-24\h\tmp\vision-object-target-bound-20261102.tar.gz
SHA256: 0688e2aaece27009ac21056d79c6f4f642aaf5a9d782dc3faab1a2e964f76782
