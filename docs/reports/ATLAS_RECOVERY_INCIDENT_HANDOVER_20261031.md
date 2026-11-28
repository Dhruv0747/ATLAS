# ATLAS Recovery incident handover — 2026-10-31

**CPU investigation: STOPPED at the owner's direction; root cause UNKNOWN.**
**Recovery incident: OPEN. Restoration NOT COMPLETE. CPU optimization NOT COMPLETE.**

## Operational state and safety impact

Last read-only verification: atlas-sensor-recovery.service inactive, MainPID=0,
NRestarts=0. Original files/configuration and Restart=always were restored; temporary
supervisor and override removed. Snapshot producer remains disabled.
Recovery's automatic fault diagnosis/reporting and bounded peripheral recovery
are UNAVAILABLE while this service is stopped. Other independent protections are
not replacements for it. Do not describe ATLAS as having fully restored recovery.

CPU75%, RAM80%, temperature below70C, E-STOP, command-zero, telemetry freshness,
watchdogs and controller protections remain unchanged. No new safety-state claim
was made during this documentation-only closure. No restarts, cameras, inference,
movement, firmware changes, speculative patches or additional tools authorized.

## Retained findings and evidence

- a2073b4: one original-Recovery start, PID374161; READY appeared briefly, then
  actual86.934673% CPU rejection. Cleanup verified;41 unrelated services unchanged.
- 1d81445: collector timeout/partial-evidence defect corrected. That earlier tooling
  failure was not proof of CPU overload. The latest rejected scan was complete.
- 88ab82f: adjacent aggregate CPU66.28->86.93%; approximately96% of the increase
  was system/IRQ/softIRQ time. This identifies an accounting category, not a cause.
- Recovery and Localization concurrent load is confirmed, but neither is proven
  responsible for the entire spike. No interrupt storm or excessive wakeup rate
  has been demonstrated. Timestamp-window kernel/network journals had no entries
  establishing a USB fault, network event or interrupt storm; silence is not proof
  of absence. Saved Nav2 user-only samples cannot identify a kernel hot path.
- ed85ebd: type-preload candidate remains OFFLINE/UNDEPLOYED, with no measured
  Jetson benefit. It is not an accepted CPU fix or a reason to restart blindly.

Do not alter/delete/reuse consumed attempt directories or markers:
Jetson /home/jetson/project-atlas-migration/recovery-restoration-1d81445
PC work/recovery-restoration-result-20261031
Earlier PC work/recovery-startup-diagnostic-evidence-20261031 and
work/recovery-attribution-evidence-20261031 retain their distinct attempts.
Latest EVIDENCE_SHA256SUMS previously verified on Jetson and downloaded copy.
Raw private evidence stays outside Git; reports and findings remain in history.

## Separate localization issue — OPEN, not attributed CPU root cause

Existing journal at2026-10-31 09:03:40–09:03:53 IST shows AMCL unable to publish a
pose/transform pending initial pose, repeated no-motion update requests and Nav2
costmap waiting for the missing map frame/transform. Warnings precede the Recovery
start and continue through rejection. No initial pose was injected; no TF changed.
Localization/navigation readiness is not established by healthy process PIDs.
Track separately; do not equate this warning with proven cause of the CPU spike.

## Evidence needed before resuming

1. Timestamp-aligned kernel call-path attribution for a comparable overload,
   including process identity and IRQ/softIRQ source attribution.
2. Per-core CPU, interrupt-source deltas and scheduler/wakeup evidence sufficient
   to distinguish DDS/network, driver/USB, scheduling and other kernel work.
3. For the separate localization issue: existing map-loading/initial-pose/TF
   history establishing why map->odom is unavailable; do not invent a pose.

Those data are not present in the saved counters/user-only profiles. They cannot
be reconstructed retrospectively from aggregate CPU alone. This is an evidence
requirement, NOT approval for new profiling, tools, startup attempts or live tests.
Resume only with new discriminating evidence and separately authorized actions.
Until then stop investigation; keep Recovery incident and localization issue OPEN.