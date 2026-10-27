# Stage 28 SWD maintenance policy and final preparation gates

2026-10-27. Design only; builds on 7e3c4dc, d36e88a and bb34186. No probe connection, Jetson query/change, MCU read, reset, stop or restart performed for this review. Existing production operation is preserved.

## Reviewed existing behavior

`atlas_sensor_recovery.py` checks fresh sustained zero commands and a fresh stop latch before base recovery. Those protections remain required. They do not express maintenance ownership: in the failed B1 attempt they permitted the competing restart.

The existing `maintenance_hold()` permits only atlas-camera.service for at most 45 seconds, using wall-clock JSON expiry. Missing/corrupt/expired entries mean no hold. `schedule_recovery()` checks it and `recover()` checks again, but the final check is not atomically serialized with the subsequent systemctl call. Adding the base to this camera allowlist is therefore insufficient.

The previously inspected base unit has `Restart=on-failure`, WatchdogSec=5 and RestartSec=3. Blocking only recovery-node dispatch does not prevent systemd automatic restart. Existing source tests intentionally confirm that camera holds cannot suppress base recovery. Preserve that behavior unless a separately reviewed SWD-specific mechanism is installed.

## Proposed policy (NOT implemented or installed)

Scope: deny **automatic base stop/start/restart operations** during one explicitly authorized SWD session, while keeping the current base process, telemetry, E-STOP/mux, fault classification, diagnostics and all unrelated recovery behavior running. Never mark stale data healthy. Do not reset recovery budgets merely because maintenance occurred.

States:

| State | SWD reads | Base automatic recovery | Exit |
|---|---|---|---|
| IDLE | Forbidden | Existing policy | Explicit single-use approved request |
| ARMING | Forbidden | Dispatch interlock acquiring | No in-flight base job, verified safety and all gates acknowledged |
| ACTIVE | Permitted within deadline | Denied | Completion, fault or deadline |
| ABORTED / DISCONNECT_PENDING | Forbidden | Denied; attention alarm | Verified probe session disconnected and operator review |
| VERIFYING | Forbidden | Denied | 30 s fresh packet progression and safe controls, then explicit release |
| RELEASED | Forbidden | Existing policy restored | Grant consumed |

The read-operation lease is bounded to the previously proposed 180 seconds with 60-second per-operation caps and a short heartbeat (proposed 2 seconds). It cannot be renewed indefinitely. Expiry or loss of owner heartbeat terminates/cancels PC reads and enters DISCONNECT_PENDING; it MUST NOT automatically re-enable base restart. This residual inhibitor is an explicit fault latch requiring acknowledgment, not an unbounded permission to keep reading. If a strictly timed automatic return to recovery is required, SWD must remain NO-GO until disconnection can be independently guaranteed.

### Admission and race control

1. Bind a one-use grant to session ID, Jetson boot ID, reviewed package hashes, probe identity, owner process identity and a monotonic deadline. Use private owner-only files/IPC and atomic state updates. Reject malformed, foreign, replayed and expired grants. No grant is created now.
2. Recovery dispatch and maintenance admission must share a per-base lock. Hold it through the final permission check and systemctl dispatch/completion tracking; merely checking a JSON file twice leaves a race. A pending or in-flight base restart blocks admission; never cancel a partially executed systemd job and assume nothing happened.
3. Require acknowledgment from the running recovery service and verified unchanged base PID before allowing PC attach. Inhibit every monitor targeting the base, not just encoder_health. Unrelated monitors remain unchanged.
4. Independently cover systemd self-restart. A candidate reviewed base-start admission condition (e.g. a narrowly scoped systemd ExecCondition integration) could deny new starts while a durable SWD latch exists without stopping the running process. This would require an approved unit/drop-in change and daemon reload, plus isolated systemd testing. It is NOT installed. Such a start condition cannot prevent another actor from first stopping the unit; all base restart callers still require audit/interlock. Unexpected service changes abort the read session.
5. On recovery-service crash/restart, an unresolved durable SWD latch must remain an inhibitor for the base. Missing/corrupt state after admission means manual attention, not permission to restart. The exact persistence/boot semantics must be tested: unexpected Jetson reboot ends permission and must not silently discard an unresolved attachment state.
6. Keep sensor freshness, E-STOP, zero-command and resource guards unchanged. On lost safety evidence cancel reads and latch attention, preserving physical isolation. No automatic reset, reconnect, probe firmware update or resume command.

This is not a claim that a maintenance mechanism exists today. Implementation, mocked race tests, isolated systemd tests and separate deployment approval are required before a SWD attempt. Do not disable atlas-sensor-recovery as a shortcut.

## Offline acceptance matrix for the future implementation

- Admission racing a queued/in-flight restart cannot yield both permission to attach and a restart.
- Each base-targeting monitor is inhibited; camera, LiDAR and unrelated monitoring are unaffected.
- Existing E-STOP/fresh zero-command tests continue passing; stale status remains stale.
- Lost heartbeat, 180-second expiry, PC crash, corrupt/deleted state after admission, recovery restart, boot-ID change and disconnected network all revoke read permission and retain the unresolved-attachment latch.
- Systemd on-failure/watchdog restart cannot start the base during the latch; original behavior returns only after controlled release.
- Duplicate grants and unauthorized release fail; no automatic retry or B2 transition exists.
- Normal finish requires probe disconnection, byte/hash checks and 30-second telemetry verification. Copy failure prevents reporting a fully replicated backup.

No new tests are claimed here: this is a design review. Existing 26 B1 tests establish only the prior UART prevention/readback behavior, not this SWD policy.

## Physical orientation review

Official schematic inspection establishes J16 net numbers: 1 +3.3 V, 2 SWCLK, 3 GND, 4 SWDIO, plus a fifth ground symbol despite a 4P footprint label. The supplied rover photographs show the exterior and steering, not a legible J16 close-up. No new board/probe photographs were attached to this request. Thus physical left/right orientation, connector mating face and pin-1 marking remain UNVERIFIED. Do not turn schematic numbering into physical wiring instructions.

Required: clear close-up of the actual J16 area with silkscreen/board revision and surrounding landmarks, plus genuine probe label and CN3 connector/keying. If photos cannot establish pin 1, a separately approved powered-down continuity inspection is required. Do not disturb wiring, expose a powered board unsafely or perform resistance checks while powered just to obtain this evidence.

## Final future attempt checklist

1. Physical pin orientation and genuine ST-LINK/V2 CN3 mapping verified; VAPP is an input, power outputs and NRST unconnected. Suitable secured adapter and safe attachment plan approved.
2. Motors/servos remain physically disconnected, transmitter OFF, normal BOOT0 state, stable existing board supply/main switch ON, E-STOP and zero commands freshly verified.
3. Installed CubeProgrammer 2.23.0, explicit SWD HOTPLUG, reviewed probe identity/frequency, no defaults to NORMAL or under-reset.
4. Independently tested maintenance policy deployed only after approval; running process and sensor health baseline recorded; grant admitted with no pending base jobs.
5. One bounded session. Stop on protection denial, ambiguous chip/size, error, timing failure, telemetry/resource/safety degradation or recovery activity. No fallback attach mode.
6. Verify unprotected STM32F103RC / 256 KB before two full reads. Compare exact lengths, all bytes and SHA256; preserve settings, identification and option-byte evidence without writing them.
7. Disconnect software session; verify telemetry progression and safety for 30 seconds. Preserve independent verified Windows and Jetson copies. Clear only this session's latch after explicit successful release; leave B2 blocked.

## Rollback and abort

No production change exists to roll back now. A future maintenance deployment must back up exact source/unit/drop-in hashes and service state and include a tested restore procedure. Never remove an active maintenance gate or restore automatic restart until SWD disconnection is established. If the board is stale or target state unknown, leave safety latched and actuators isolated, retain evidence, and request a specific recovery action; do not reset/restart automatically.

After successful disconnection and healthy telemetry, restore only files/settings introduced by the maintenance package, verify hashes and existing recovery behavior, and perform only separately approved reload/restart actions needed for rollback. Do not alter maps, calibration, firmware, camera configuration or unrelated services.

## Verdict and next approval

**NO-GO for SWD hardware execution.** Safest immediate next step is physical identification evidence, followed by offline implementation/validation of the scoped policy. Subsequent maintenance installation and one read-only HOTPLUG session require separate explicit approval naming any necessary unit changes, daemon reload or service restart. The current request authorizes none of those live actions. B1/UART retry and B2 flashing remain NOT APPROVED.
