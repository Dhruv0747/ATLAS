# Protected publisher gates — preparation only, 2026-11-02

## 2026-11-03 offline controller acceptance

The Mux transaction now binds the prepared archive, installation and exact rollback,
effective unit and drop-ins, process identities, one durable activation reservation,
and independent cleanup. The previous incomplete controller notes below describe
the November 2 candidate.

Both systemd phases inherit the same launch-time CLOCK_BOOTTIME origin. The worker
uses up to 60 seconds. Cleanup uses at most 30 seconds and must finish within 90
seconds of launch. An expired deadline leaves an incomplete incident open for
manual assessment. Recovery of the transaction cannot grant additional time or a
restoration restart. While publication safety is unavailable, admission fails.

Thirty-five new offline checks passed in Ubuntu WSL, using the private staged archive,
scratch Linux files, fake Mux services, and real process interruption and timers.
Independent review covered the policy, files, transaction and acceptance paths.
The original eight checks and earlier integration suites were excluded.

Deployment remains blocked on an independent maintenance protection method
covering Mux downtime and electrically verified actuator isolation. The November 3
read-only inspection also found active Mux PID 1909 versus staged PID 1897.
The controller refuses that binding. After protection is established, review and
bind the then-current boot, services and configuration before fresh admission.
Yahboom remains separately gated.


Continues3994fd9. No live writes/restarts/subscriptions. Current read-only binding:
mux PID1897,NRestarts0,Restart=always; base PID5062,NRestarts0,Restart=on-failure.
Recovery PID1982/Web2126 remain untouched. Original publisher hashes unchanged:
mux e70df2baf9f77ef688d253a93f091394b33686f3f88a85ba8d7fd9c9ef6cc033
base bb6db3a10c196be55ccd1bcb7bcbbf538643089c1a7bd5fe833f9b45453b473d.
Helper absent. Exact source metadata still matches prior uid/gid/mode/mtime/xattrs.
Boot identity, /proc start ticks, unit hashes/policies and file metadata retained in
private binding.json; must be rechecked before any future installation.

Private preparation packages in C:/Users/Dhruv/Documents/Codex/2026-07-24/h/tmp:
- publisher-mux-provenance-prep-20261102.tar.gz
  SHA256 7b24c8792f7a93474be85c7f8c969be225ed9699f78b5c6b3d7bf66657296514
- publisher-yahboom-provenance-prep-20261102.tar.gz
  SHA256 851f19c7d362a100b821b97f8329367c7a7683254d4b3b283eab190ff86e2fe3

Each includes minimal candidate payload, exact original publisher bytes, original unit
backup (not an installation target), binding and INSTALL_PLAN marked BLOCKED_NO_EXECUTION.
Mux adds one helper; base requires the identical mux-installed helper. No executable
installer or restart command is supplied. All regular members0644; native Linux extraction
and all11 manifest entries PASS. Prior33/15 tests and exact-live reversal reused.
No control logic changed: exact-live AST checks previously established preservation of
FlySky/controller selection, arbitration, encoder/RC processing and E-STOP branches.
This does not constitute live control acceptance.

## Independent supervision gate — FAIL readiness

Existing source-only observer may supervise Web downtime once publishers are active,
but during mux restart policy/command production disappears; during base restart
encoder-health production disappears. Recovery/HTTP observing those same topics cannot
manufacture independent fresh source evidence. Original processes expose no complete
provenance until restarted. Existing observer must reject missing/expired observations;
there is no source-time refresh, grace period or assumed stationary fallback.
No evidence establishes these restarts finish within existing freshness bounds. Previous
CPU rejection remains unresolved. Web-only restart controller is not a protected publisher
controller; do not merely substitute unit names. No framework or controller created here.

## CPU admission/acceptance specification — READY; execution BLOCKED

Reuse existing /proc/cgroup collector and existing safety checker, no new ROS participant.
Before each independently approved operation: three consecutive valid one-second samples,
CPU strictly<75%, RAM<80%, every required temperature<70C, E-STOP latched/manual-only,
commissioning false, zero six-component commands, stationary encoders and LIVE telemetry.
Record original identities/counters before start. Continuously enforce existing limits,
including first startup interval, and preserve every rejection plus partial evidence.
No exemptions for startup, missing counters or slow collection. Validation at most20s;
proposed operation cap60s plus existing bounded cleanup, only once a compatible existing
controller/supervision path is reviewed. These are acceptance bounds, not evidence of fit.
CPU/RAM overhead remains UNKNOWN; prior network observer synthetic numbers do not apply.

## Sequential gates

1. Mux: NO-GO until independent safety during downtime is established. Future approval
must name installation+one restart of atlas-cmd-vel-mux.service, Restart policy handling,
resource supervision, exact rollback and bounded restoration authorization. Admission or
identity drift aborts before mutation. Failure prevents all Yahboom operations.
2. Only after Mux is ACTIVE, verified with source provenance and unchanged safety/control
behavior, re-read identities and take fresh safety/resource admission. Rebind base package
because mux PID/start ticks have changed; old binding cannot be silently accepted.
3. Base: separate NO-GO until independent encoder/source-loss handling is established.
Future approval must explicitly name rover-base-telemetry.service installation+one restart,
with independent safety and rollback. No automatic chained restart or retry.

Rollback preparation PASS for bytes/metadata: restore only respective original script
if installed hash matches candidate; restore original unit policy exactly. Unit backups
are evidence, not permission to overwrite configuration. Helper removal only after all
candidate users are reverted and if its hash matches the installed helper. Never remove
helper while the base candidate imports it. File restoration does not restore running code.
If safe restoration restart cannot be justified, leave affected service stopped and incident
OPEN; do not restart Recovery or other services as an improvised recovery.

Final: both executable installation packages BLOCKED; independent supervision FAIL readiness.
There is no current execution approval request. Missing prerequisite is verified independent
safety observation across each protected publisher's downtime at unchanged limits. Until
that is supplied, stop at preparation; no further restart experiment is justified here.

## Owner confirmation — 2026-11-02, inactive staging follow-up

Owner explicitly confirms M1–M4 motors and S1/S2 steering servos disconnected,
with no alternate actuator power connections. Record as owner-reported physical
configuration, not electrically verified isolation. Do not request this confirmation
again unless the configuration changes. No connection was touched or measured.

Outstanding supervision constraint: the existing Safety/SourceConsumer requires
fresh policy and command evidence originating in Mux. A separate observer process
or Foxglove bridge does not make that source independent. SourceConsumer also pins
process identity, so a replacement Mux requires independently validated re-binding;
it cannot inherit the old process's healthy evidence. Existing restart_policy.py
is explicitly web-only in production and cannot be relabelled as an approved Mux
restart procedure. Physical actuator disconnection reduces motion exposure but
neither generates fresh E-STOP policy nor changes the current safety contract.

Bounded procedure remains blocked BEFORE production writes or service stop. Keep
staged archives and exact-byte originals unchanged. No restart command is issued.
The proposed 60-second operation / 20-second validation bounds remain proposals,
not an executable validated supervisor. Missing/expired source evidence must abort;
no grace period, cached healthy substitution or automatic restoration start is
approved. CPU <75%, RAM <80%, temperature <70C and all freshness limits unchanged.

To remove this gate under the unchanged contract, evidence must identify an
existing authoritative policy/command source that remains valid independently of
Mux and Web, including verifiable freshness and identity. None is established in
the reviewed implementation. A hardware-isolated maintenance procedure would be
a different safety contract requiring explicit review/authorization, not an
implicit consequence of this disconnection confirmation. Yahboom remains separately
gated. No tests repeated: documentation-only update, no runtime code changes.

## Bounded Mux sequence review — 2026-11-02 (NOT executable)

Owner also reports E-STOP pressed and no observed movement. This is pre-operation
owner evidence, not continuous hardware-inhibit evidence. No reconfirmation requested.

Existing reusable primitives: restart_policy.Policy provides durable one-use restart
reservations and exact drop-in ownership; recovery_snapshot_runtime.Transaction.command
provides nonblocking systemctl polling with a separate safety check and bounded client.
Neither is a ready Mux deployer: Policy is production-pinned to Web; Transaction adds
ATLAS_RESTART_SNAPSHOT=1 and its finish requires a restoration restart. Do not invoke
these classes with a substituted Mux unit. Their semantics must be reconciled before
an executable Mux transaction is claimed ready.

Conditional sequence, only after independent protection is verified:
1. Bind original/candidate/helper/unit hashes, PID+start ticks and exact-byte rollback;
   refuse prior transaction markers, file drift or an existing service job.
2. Establish independent maintenance authority and resource observer BEFORE mutation.
   Require fresh policy, six zero command components, encoder data and latched E-STOP
   at admission; CPU<75%, RAM<80%, all required temperatures<70C. Never refresh ages.
3. Durably reserve a single activation. Temporarily control only Mux Restart=no with
   owned runtime drop-in; use nonblocking service jobs and independent crash cleanup.
4. Install only reviewed Mux/helper files, verify bytes, restart only Mux once.
   Proposal: at most60s worker and20s acceptance inside that worker; cleanup has a
   separate explicit bound to be validated, not an implied 60s total guarantee.
5. Missing Mux evidence remains UNAVAILABLE and the current safety contract rejects
   it. There is currently NO approved alternate maintenance authority. Therefore
   step2 is BLOCKED, and steps3-4 MUST NOT run. No grace period or cached PASS.
6. Acceptance must independently verify new PID/start ticks, source identity/sequence,
   fresh policy and exact command evidence, unchanged E-STOP/manual-only state, fresh
   encoder health and resources, then restore original restart policy and verify it.
7. Failure before restart: restore any owned file writes/policy while retaining the
   original process where verified unchanged. Failure after restart: stop/quiesce only
   Mux, verify exact original file bytes and original policy restoration. No automatic
   restoration start: it needs the same missing independent protection. Preserve the
   incident if cleanup fails; never claim rollback bytes prove runtime recovery.

Remaining before activation: (A) independently verified maintenance protection that
can meet an explicitly reviewed safety contract while Mux data is unavailable;
(B) minimal Mux-specific binding of existing transaction/cleanup primitives, with
focused checks of that new binding and concrete cleanup deadline; (C) fresh admission
and explicit execution approval for that reviewed artifact. Existing package and
integration suites are not repeated. Yahboom requires separate later approval.

# Controller candidate, not activation readiness

The offline Mux-specific policy candidate is in
`project_atlas/tools/vision3d/mux_restart_policy.py`. It reuses Policy state and
owned-drop-in restoration, pins Mux, uses bounded nonblocking systemd clients,
prohibits restoration restarts and blocks admission because no independent
maintenance authority is implemented. It is NOT an installer or runnable command.

Its proposed cleanup budget is 30 seconds, with a 60-second worker budget. Focused
mock checks do not establish a hard wall-clock bound for filesystem stalls,
kernel-uninterruptible work or systemd cleanup. A systemd outer bound and exact
file/metadata rollback integration still require validation before readiness.
Existing staged packages and live services have not been changed.

Independent review found cleanup-mode restart and inherited live-policy restoration
paths in the offline candidate. Both now reject explicitly; targeted regression
added. Eight focused WSL offline checks pass. Full binding remains incomplete:
cleanup budget is per object, not durable across supervisor reconstruction;
file rollback and outer timeout integration are not verified. Do not deploy this
candidate or claim its 30-second cleanup is a verified transaction-wide deadline.
No old suites rerun, package rebuilt, live write or service restart performed.


## Per-attempt binding and maintenance-protection interface (2026-11-03, offline)

**Binding.** The hard-coded `BINDING_SHA` is removed. The sealed `binding.json` stays pinned through
the reviewed manifest, and still provides the publisher bytes, metadata and unit configuration used for
exact-byte rollback. Boot and process identity now come from a per-attempt snapshot
`mux-attempts/<sha256>.json`. It is trusted only when all of these hold:
- the owner approved that exact SHA256 at launch (`ATLAS_MUX_ATTEMPT_SHA`); a file never vouches for itself;
- it names the sealed archive and manifest;
- it is for the current boot and was captured at most 900 s earlier;
- it lists exactly the sealed services with unchanged unit hash, fragment and `Restart`;
- it contains no duplicate JSON keys.

PID plus `/proc` start ticks, `NRestarts`, drop-ins, dependencies and file bytes/metadata are re-checked
live before and after the single restart. Each attempt gets its own transaction directory. A new
transaction is refused while any earlier `mux-transaction-f95c9d2*` directory exists. The check uses
`os.listdir`, so an unreadable directory refuses rather than passes.

**Pre-mutation safety admission (new).** Before the first mutation (drop-in, file swap or restart),
the original Mux must show all of the following in at least 3 consecutive, advancing, fresh snapshots:
- E-STOP latched, manual-only, commissioning off, source STOPPED;
- six zero command components;
- LIVE, stationary encoders.

This uses the existing `Safety` evaluator. The replacement acceptance (`verify_replacement`) is unchanged.

**Maintenance protection interface.** `independent_check()` delegates to a protection object.
- The default `Unavailable` still always refuses with the original message.
- `AttestedIsolation` accepts only owner-approved (`ATLAS_MUX_PROTECTION_SHA`) measured evidence:
  - for this boot, measured at most 900 s before start, with bounded validity covering the whole
    60 + 30 s window;
  - M1–M4 and S1/S2 connectors open and measured dead (no more than 0.2 V, no PWM) on battery
    power and on USB-only power;
  - USB backfeed checked;
  - battery DC-DC and Jetson USB 5 V paths isolated;
  - all four automatic-restart units covered.
- Owner confirmation alone, a photograph or a single reading is rejected.
- This is a recorded physical lockout state, not live sensing. Reconnecting an actuator during the
  window cannot be detected and must be prevented by the lockout procedure.

**Open owner decision (required before any use).** The earlier record treats the missing prerequisite
as *independent safety observation across Mux downtime*. It says physical disconnection "neither
generates fresh E-STOP policy nor changes the current safety contract". Accepting measured isolation
in place of that observation changes the safety contract, so the owner must approve it explicitly.
Until then the sealed `INSTALL_PLAN.json` stays `BLOCKED_NO_EXECUTION` with restarts unauthorized,
and no evidence file exists. Activation: **NO-GO.**

**Known limit.** Cleanup does not re-verify its copied attempt and evidence records against the launch
pins. Cleanup is still gated by the journal and the origin deadline, so its behaviour is unchanged.

Validation: 66 focused offline checks, run as uid 1000 with the reviewed archive. This covers the
attempt binding, PID-reuse and replacement rejection, the evidence bounds, pre-admission refusal
cases, admission order and the one-transaction check, plus the 43 earlier checks.

### Re-review fixes (2026-11-03)

- **Pre-admission now uses the existing consumer rules** (`existing_safety_snapshot.verify_bytes`, the same
  checks as `verify()`): size limit, observation shape, the raw `encoder_packet_monotonic` age of at most 1 s,
  producer freshness of at most 0.75 s, and the Safety contract.
- **The original Mux must still be publishing:** across the samples, the publication time **and** both the
  policy and command receipts must advance.
- **Second check before the restart:** one fresh safe snapshot is required immediately before the single
  restart, after the file install. If it is unsafe, the restart does not happen and cleanup rolls back.
- **Snapshot trust:** the file and its directory must be owned by the transaction uid; the file must have no
  group/other bits, and the directory must not be group- or other-writable. Symlinks are refused.
- **Readiness probe before any journal:** a missing, untrusted or unsafe observer refuses before the
  transaction directory exists, so it cannot consume the single attempt.
- **Prerequisite (not met today):** the snapshot producer (`/run/user/1000/atlas-restart-safety/state.json`) is
  written only by `atlas_sensor_recovery` with `ATLAS_RESTART_SNAPSHOT=1`. The 2026-10-31 and 11-02 records show
  it disabled and the file absent. Enabling it is a separately gated Recovery environment change and restart.
  The attempt binding must be captured **after** that change, because it pins Recovery's PID.

Validation: 75 focused Mux checks plus the existing snapshot-validator suites (92 in total), run as uid 1000
with the reviewed archive. `test_production_snapshot.py` needs `ATLAS_SNAPSHOT_REVIEW` and errors identically at
the base commit, so it is unrelated.
