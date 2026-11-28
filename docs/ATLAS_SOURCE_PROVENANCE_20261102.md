# Source provenance — offline implementation, 2026-11-02

Scope: additive metadata only in existing mux/control-policy and base/encoder-health
publishers. No new ROS topics, nodes, timers, command arbitration or fault thresholds.
No deployment, restarts, camera, inference or monitoring latch operations.

Mux wraps every existing /cmd_vel publication, including all direct stop and shutdown
paths, with a conservative timestamp taken immediately BEFORE publish. It records
all six exact published components only after publish returns, with a sequence.
The existing control-policy JSON carries this command plus an observation timestamp,
boot UUID, PID and /proc process start ticks. Unstamped Twist is unchanged and is NOT
independently promoted to a fresh safety observation. A publication timestamp proves
host publication, not MCU application or motor state. Identity failure yields missing
provenance and consumer rejection; no zero-value substitution.

Encoder health preserves the existing rounded packet age and adds its calculation
monotonic time, original host encoder packet receipt time, process identity, health
sequence and existing encoder-update sequence. MCU acquisition time remains unknown;
these are host-source observations, matching the existing packet-age contract.
No thresholds or encoder fault behavior change.

Opt-in SourceConsumer in existing_safety_snapshot.py consumes policy and encoder-health
source envelopes, with identities independently pinned by its caller. It does not trust
Foxglove/receipt timestamps or learn identity from the first incoming message. It rejects
wrong boot/process, missing/invalid/future/stale evidence, replay/regressing sequence or
time, regressing encoder packet/update counters, nonzero commands and unsafe policy.
Deep-copied admitted values cannot be mutated by transport callers. Any failure/disconnect
latches the session unsafe. Same command/packet can recur only while its original timestamp
remains valid; polling cannot renew it. Age limits remain observation<=1s,
output<=0.75s, encoder packet age+observation age<=1s. Millisecond rounding tolerance
checks representation only; raw packet timestamp independently enforces the 1s ceiling.
Buffered data older than the limit or replayed/out-of-order data rejects. Queuing within
that age window cannot be inferred solely from timestamps; no zero-latency claim is made.

33 focused offline tests PASS: provenance/identity/stale/missing/disconnect/replay,
exact boundaries, mutation isolation, encoder regression, six-component capture,
all publication paths instrumented, existing stop-hold and mapping-limit behavior.
No full regression suite or previous deployment tests repeated. Python source parses.
Independent review findings corrected; no physical acceptance claimed.

CPU overhead UNKNOWN on Jetson. Added work is one startup identity read per publisher,
scalar metadata and small JSON expansion; no per-message /proc reads, new ROS participant
or background loop. This is not a measured upper bound or proof against startup overload.

Deployment NO-GO. Repository publishers differ from live versions (live FlySky/Stage28
changes must survive a targeted patch); never overwrite live publishers wholesale.
SourceConsumer is not wired into the Web restart supervisor or a live Foxglove reader.
Next offline step: exact-live three-way patch reconciliation, then a bounded receive-only
transport binding that preserves source identity and ages. Any later protected publisher
installation/restarts require separate explicit approval for atlas-cmd-vel-mux and the
active yahboom base service, with fresh safety, CPU admission and exact rollback. Recovery
must remain untouched. No execution command or activation package is prepared here.
