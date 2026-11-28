# Owner-authorized restoration retry after Xbox B — FAIL — 2026-10-31

Owner confirmed B pressed and explicitly authorized retry. Fresh independent checks
verified E-STOP latched,zero fresh commands,stationary encoders,LIVE telemetry;
CPU59.14–61.65%,RAM<59%,temperature<=62.75C. New single-use stage preserves earlier
consumed attempt. Same reviewed code; only outer-unit stage paths changed. Manifest
85d439f4dd60e40cb8b1c4cdc967cd5e886620d72cc320243c8a0e773861853b.

Execution preflightCPU61.063%,RAM59.076%,temp62.625C. Original recovery script was
restored and verified as5f44cc1fbd7cdc65b8af17abeb9ecd41cec0a8c8f3ee8274fa9b34362633193a.
Exactly one recovery start attempted under Restart=no. Independent watcher rejected
CPU93.624161% (mono53860.589931); stopped immediately, no retry/restoration start.
This occurred with ORIGINAL code and snapshot producer disabled; it is not proof
that snapshot writes caused earlier startup overload. Exact process attribution
at rejected interval not captured by current fail-fast watcher.

Cleanup verified: original policyRestart=always restored, no temporary override or
snapshot runtime; recoveryPID0,failed/STOPPED,NRestarts0. Candidate backup retained.
No valid readiness confirmation; incident remains OPEN.

Postflight:CPU59.091/58.598/59.625%,RAM58.376–58.455%,temp62.687–62.781C; all E-STOP,
zero-command,stationary and fresh telemetry checks pass. Full service diff showed
ONLY the optional restoration supervisor changing active->failed. All protected
rover identities unchanged,DashboardPID182915 remains active. Initial postflight
boolean included the trial unit and was false; explicit diff resolves it as expected
trial exit, not a protected-service change. Do not discard that original observation.

Evidence:/home/jetson/project-atlas-migration/recovery-original-restore-retry1-20261031/
result,health,transaction,cleanup,postflight,samples,journal and EVIDENCE_SHA256SUMS.
Checksums verified; trial unit removed after exit,daemon-reload only. No camera/AI,
movement,firmware,controller changes or PR merge.

NO-GO for another start. Diagnose original recovery startup cost offline before a
new bounded restoration proposal. Do not relax75%CPU/80%RAM/<70C guards or retry
without owner approval. Original source restored, but service NOT operational.
