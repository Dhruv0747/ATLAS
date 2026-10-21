# Stage 32: depth admission failure, 21 October 2026

## Confirmed evidence (read-only investigation)

Baseline: developer branch fast-forwarded to `3e9cbaa`; existing U2+P rendering and calibration work preserved.
Owner reports an earlier preview containing 3,211 points. That exact successful session's telemetry was not independently recovered; the count is owner-reported, not a new measurement.

The current persisted viewer state is OFF, depth, elapsed 1.200403347 s,
sample_count 0, driver_stopped true, reason `Astra identity/access changed`.
Runtime source runs three admission samples before spawning the driver. This
failure is therefore before normal streaming, not evidence of a depth conversion
or rendering defect.

Current interfaces match the previously approved addresses and VID/PIDs:

| Role | Device node | VID/PID | Physical USB path |
|---|---|---|---|
| OpenNI depth/IR | /dev/bus/usb/001/014 | 2bc5:0403 | 1-2.3.1.2 |
| RGB | /dev/bus/usb/001/011 | 2bc5:0501 | 1-2.3.1.1 |

Both nodes are root:root 0664, with no named jetson ACL. The web owner is jetson,
not a member of root. Both os.access(R_OK|W_OK) checks failed; a read-only diagnostic
open(O_RDWR), with immediate close on success and no read/write/ioctl, failed with
errno 13 Permission denied on BOTH nodes. No OpenNI initialization was attempted.
Earlier operator-supplied getfacl output showed jetson:rw on these nodes.

The current boot is new (uptime-s reported 20:31:37; uptime roughly 448 seconds
during inspection), whereas the accepted deployment was at 19:17. Temporary
device-node ACLs do not survive recreation at reboot/replug. This explains the
observed missing grants; the old boot's exact node removal event is unavailable.
No current address change is observed. USB serial descriptors are absent; SDK
serial 17122120830 in the existing manifest cannot be independently reconfirmed
without SDK access. Do not confuse missing USB serial with changed camera identity.

Retained current-boot logs contain no attributed Astra disconnect/reset,
overcurrent or undervoltage event. A generic xUSB slot15 ep6 buffer-overrun warning
exists but cannot be attributed to Astra. Hub/power failure is NOT established.
Kernel wall time changed during boot; wall-clock log ordering alone is unreliable.

## Minimal candidate and limitations

The actual blocking condition is denied write access, not calibration. The guardian
previously collapsed identity mismatch and ACL loss into one message. Candidate
`stationary_ros_probe.py` separates these failures, reports the exact path/VID:PID,
bounds lsusb queries to two seconds, and fails closed on query errors. It neither
grants access nor changes the approved node selection. Hard-coded ephemeral paths
remain a documented limitation: if addresses change, stop and revalidate identity;
do not silently select a different camera. Automatic device selection is not needed
to correct this incident and is deliberately outside this small change.

No production files, permissions, services, driver modes, Domain77, calibration,
rendering, navigation or safeguards changed. No camera session or recording started.
The live stop endpoint reported latched. This is NOT a fresh camera-test admission.

## Proposed deployment and rollback — approval required

1. Recheck stopped/E-STOP/zero commands/recorder OFF, resources and exact device
   identities and live hashes. Abort on mismatch.
2. Save the current probe file/hash and getfacl output for both freshly verified
   nodes in a timestamped backup outside recordings.
3. Install only the tested diagnostic probe, verifying its hash. No existing
   production service restart should be needed for the next newly spawned worker.
4. With administrator approval, grant only jetson rw access to those two verified
   nodes using setfacl. No chmod 777, hub reset or system-wide rule. Recheck access.
5. Only with explicit camera-test approval, run ONE guarded Depth-only preview.
   Calibration is not required for the existing UNCALIBRATED diagnostic preview.
   Success requires actual depth frames and browser-rendered points.

Rollback: restore the saved probe bytes and verify their original SHA256; restore
the saved per-node ACL with setfacl --restore only after revalidating the same nodes.
No live backup was created because installation is not authorized yet. A targeted
persistent device permission policy can be reviewed separately; a temporary grant
alone does NOT promise persistence through another reboot/replug.

## Offline validation

Six new USB tests pass: both interfaces accepted, depth ACL loss, RGB ACL loss,
missing/renumbered/wrong identity, query failure/timeout, bounded read-only queries.
Eight existing Stage30 safety/CPU tests pass. No real device used by these tests.
Windows broad Stage32 run encountered missing numpy, optional dependencies and
text-encoding failures; these are not reported as passing regressions.

WSL Ubuntu22.04 Stage32 suite: 75 tests, 62 passed, 11 skipped, 2 failed.
Both failures are in the existing IR-mode-override historical byte-hash fixture:
reconstructed old runtime hash 89878d8b... differs from expected454dd25f..., so the
override tool correctly refuses UNKNOWN bytes. That test, its override tool and
runtime are unchanged by this candidate; no hashes were relaxed or rewritten to
make tests pass. This broader suite is NOT all green. The scoped USB/safety
candidate passes14 tests, but deployment remains subject to review and approval.

## Approved recovery attempt: administrator prerequisite blocked

Owner approved scoped recovery and one conditional Depth-only test. On21October
at approximately20:44 IST, fresh read-only checks found:

- Branch synchronized with GitHub at baf4ca52eb48da8ce7bc511bf7add94131435b0c.
- Live probe SHA256 f6321da4961482064a6d278e368efbb25540d5a3178ee14900255972b269a384.
- Live runtime SHA256 fc807489b06699d73efdd246913849a3d11315d6bfcba707eedd0e1381c9b5aa.
- Both expected USB identities/nodes still present; ACLs still root/root0664,
  no named jetson entry. Camera state OFF; no new session invoked.
- Three resource samples: CPU73.2026%,71.6981%,70.4293%; RAM66.6887%,66.7793%,
  66.7498%; maximum required-zone temperature59.875C. Existing limits unchanged.
- Every sampled policy: stop_latched=true, manual_only=true,
  commission_armed=false, source=STOPPED, zero commands, recorder inactive.
- Available disk394397417472 bytes.
- Protected services active, identical PIDs before/after, all NRestarts=0:
  camera1824, telemetry3293, mux1814, EKF2868, localization4595, LiDAR1815.
- sudo -n true failed: `sudo: a password is required`. sudo policy permits
  passwordless shutdown only; this does not authorize or enable USB ACL writes.

STOPPED before installation or permission mutation. No recovery backup needed or
created yet because no production file changed. Existing backups remain intact.
ACL state remains exactly the original no-jetson-grant state. No test consumed,
no frame/FPS/point/browser-interaction result exists for this attempt. Fresh full
admission and rollback preparation remain necessary after administrator access is
arranged; these samples are not reusable authorization to bypass later checks.

## Persistent permissions proposal — NOT installed

Prefer a dedicated least-privilege Astra access group with an explicit udev rule
matching USB device subsystem/type and only vendor2bc5/product0403 and0501, plus
the verified parent port topology if binding to this installed pair is desired.
Grant group read/write only (0660), not world write; add only the service user
jetson to that dedicated group. Avoid generic video/dialout grants or all-USB rules.
There is no USB descriptor serial to pin; SDK serial cannot be used as a udev USB
attribute. VID/PID-only matches any identical model, so topology restriction is
important if that is not acceptable. Port changes must fail closed and be reviewed.

Before approving a concrete rule, inspect existing udev ownership, rule order and
device parent attributes; test rule matching without triggering USB or restarting
services. Group membership may require a future service/session restart to take
effect, which is NOT authorized here. Retain guardian identity/access checks.
Rollback would remove only the new rule and dedicated membership, restore saved
device permissions, and verify original behavior at an authorized future reconnect.
This proposal is separate from today's temporary ACL restoration; no rule,
membership, permission, service or reboot change has been made.
