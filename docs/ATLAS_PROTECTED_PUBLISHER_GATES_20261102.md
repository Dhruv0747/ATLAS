# Protected publisher gates — preparation only, 2026-11-02

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
