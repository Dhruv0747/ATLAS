# Planned-reboot Recovery update — install / evidence / rollback plan

Package dir on Jetson: `~/project-atlas-migration/recovery-reboot-4af4ddad/` (exact path enforced).
Candidate `4af4ddad…` = live `5f44cc1f…` + reviewed exact-live snapshot patch + type preload.
Snapshot producer DISABLED (no ATLAS_RESTART_SNAPSHOT in unit, drop-ins, the unit's EnvironmentFile
`~/.config/project-atlas/hardware.env`, or the user manager environment; arm/install abort if found).

## Pins checked before anything changes (arm.sh / install.sh)
- Package SHA256SUMS; package location.
- Live script `5f44cc1f…`, jetson:jetson 644. Helpers on Jetson: existing_safety_snapshot.py `e37cfd13…`,
  restart_safety_observer.py `a26b364f…` (not shipped, not replaced).
- Recovery unit `1b1010ef…`, only drop-in gnss-disabled.conf `ca513ea0…`, Recovery currently active.

## Two separately approved reboots, in order
1. **Baseline boot** (`arm.sh baseline`): production unchanged; only the read-only boot monitor is enabled
   (`enable --no-reload`, no daemon-reload). Answers whether the CURRENT Recovery boot start meets the
   unchanged 75 % / 80 % / 70 C limits. If it fails, the candidate cannot pass either (same startup path,
   producer disabled) and the policy decision returns to the owner. Do not proceed to step 2.
2. **Candidate boot** (`arm.sh candidate`) only after a baseline PASS: exact-byte install + monitor in
   candidate mode. Install immediately before the approved reboot: Recovery has Restart=always, so a crash
   between install and reboot would start the candidate outside the monitor.

## Boot evidence (boot_monitor.py, one-shot per arming, no ROS)
1 s samples for 300 s: whole-Jetson CPU, RAM, hottest thermal zone, Recovery cgroup CPU/PIDs,
ActiveState/NRestarts. Written to `~/project-atlas-migration/boot-evidence-<boot_id8>/`
(samples.jsonl fsynced each second, summary.json at end). The monitor is ordered Before= Recovery
(ordering only), so Recovery's start window is observed.

Start observed = Recovery appeared after sampling began, or had used <= 50 ms CPU when it began (it is
forked milliseconds after the monitor; its startup is ~1.7 CPU-s). Recovery's start is not delayed.
systemctl timeouts under boot load are recorded per sample, never fatal, never a restore trigger.

PASS only if: Recovery's start was observed; the full 120 s window after it was recorded; every sample
in that window had CPU < 75 %, RAM < 80 %, temperature < 70 C; Recovery active with NRestarts=0 at the
end; no fail-closed action. Pre-Recovery boot samples are reported (pre_recovery_peak_cpu) and are not
used to excuse anything; reboot is not an exemption.

## Fail-closed
- Candidate mode, Recovery failed or restarted: original bytes restored at once (exact, atomic, 644,
  original mtime). systemd's existing policy runs the original next. Monitor never starts/stops/restarts.
- Candidate mode, any FAIL (incl. a limit breach): original bytes restored at the end of the window.
  The running process is not stopped: the measured spike cannot be undone and stopping removes sensor
  recovery. Snapshot stays disabled; the result is a candidate REJECTION.
- Unknown script bytes are never overwritten. Baseline mode never touches the script.
- Monitor absent/crashed: no PASS exists, so the candidate counts as not accepted; run disarm.sh.

## Rollback
`disarm.sh` at any time: disables/removes the monitor unit (--no-reload) and restores `5f44cc1f` bytes
with jetson:jetson 644 and original mtime if the candidate is installed. No restart, reload or reboot.
