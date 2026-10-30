# Vision Lab installation diagnosis and corrected offline package

Verdict: offline verifier fixes PASS; another installation and live AI test NO-GO
pending resolution of the restart CPU rejection. No deployment, restart, camera,
inference, movement or firmware operation was performed during this investigation.
Only existing journal/service metadata was read from Jetson.

## Confirmed failure order

| Monotonic seconds | Evidence |
| --- | --- |
| 22145.477145353 | installer requests web restart |
| 22145.484842 | journal: old web service stopping |
| 22146.439868794 | end of 1.000281028s CPU sample:79.145299% |
| 22147.582186 | journal: old service stopped |
| 22147.586605 | journal: candidate service started |
| 22147.613828001 | systemctl restart returned |
| 22148.642772 | rollback stops candidate after connection-refused postflight |
| 22148.651136 | original service started again |

The CPU window began just before the stop request and ended before the old process
exited. It cannot measure candidate initialization or new AI inference. The trace
contains aggregate CPU only, with no synchronized process/cgroup deltas. Whether
old-process teardown, ROS/DDS peers, polling or other simultaneous work caused the
spike is UNKNOWN. One rejected sample cannot distinguish transient from sustained.
No CPU savings are claimed and75% remains unchanged.

The actual HTTP failure was TCP connection refused, not an HTTP API error response.
The installed unit is Type=simple with a shell sourcing ROS before Python launch.
systemd activation is not HTTP readiness. The original code returned healthy later
without additional intervention. This confirms a verifier readiness race. The
candidate was rolled back about one second after launch, so evidence cannot prove
that its API would eventually have become healthy or exclude another latent bug.
No backend defect has been demonstrated; all reviewed backend bytes remain intact.

## Camera authority

Existing ViewerSession.status(), when self.child is None, returns OFF/reason only.
The existing web summary applies bool(runtime.get('driver_stopped')), yielding
false for that absent field after every fresh web process. No camera is started by
that path. Missing driver_stopped is not a positive stopped assertion.

The installation verifier now requires OFF from the API and two surrounding kernel
process inventories with no existing Astra executable, runtime --worker or optional
AI worker. Unreadable/incomplete identity, an active worker or non-OFF API rejects.
The original reported boolean is retained verbatim in evidence; it is not rewritten
to true. This resolves deployment interpretation without modifying camera runtime,
camera controls or summary semantics. It is a point-in-time read-only check, not a
promise against another actor launching a process afterward.

## Narrow corrections

* New install_verification.py waits at most10s for HTTP readiness. Each request is
  bounded2s; only connection refused is treated as startup unavailability. HTTP
  errors, malformed data and timeouts fail immediately. Deadline expiry rejects.
* Resource failure is latched and checked before HTTP polling and after each
  response. This exact saved79.15% condition would still abort before waiting.
* Observer outage is recorded NOT_OBSERVED, never PASS. Fresh complete E-STOP,
  command-zero, encoder, telemetry, recorder, CPU/RAM/temperature checks remain
  mandatory after readiness. Resource monitoring continues during web restart.
* Monitor records subsequent bounded samples after a rejection, preserving the
  initial failure. Primary exception, resource failures and rollback error are all
  saved. Historical failures cannot authorize installation after CPU settles.
* Rollback gets the same bounded HTTP readiness observation, followed by fresh
  safety validation. It restores only the exact three backups and removes only
  matching candidate additions; concurrent changes prevent destructive overwrite.
* Browser verifier checks OFF and records the raw driver flag; installer kernel
  evidence remains separately mandatory. Six cards/24 disabled controls, preview,
  white-glass CSS, navigation, overflow and no non-GET requests remain checked.

No UI, backend, model, driver, threshold, production service or TF file changed.
The packaged backend is still execution-disabled and is the reviewed52d6b15 bytes.

## Focused offline tests

13 unittest cases PASS on PC Ubuntu WSL, simulated processes/services/files only:
readiness refusal then success; bounded deadline; latched CPU before HTTP; HTTP500,
timeout and malformed JSON rejection; invalid status shape; guard failure after
response; OFF/false plus process authority; conflicting/unknown camera state;
process appearing between observations; kernel identity matching/incomplete-entry
rejection; multiple-error preservation; exact saved timestamp ordering; complete
fake installation/readiness failure/exact rollback plus single-use refusal.
Browser verifier syntax PASS. No new live browser or camera validation performed.
Unchanged21 backend preparation tests are reused, not rerun.

## Corrected package and rollback

PC-only package: `work/object-target-corrected-install-review` beside the worktree.
It contains the unchanged original16 artifacts plus installer, verification helper
and browser verifier. Nothing was copied to Jetson for this new candidate.

DEPLOYMENT_SHA256SUMS SHA256:
`a586c2d22276ef4f7385387a79cadd581b2c7a52567d89a8754ee051b9c99e68`.
Installer SHA256:
`bd29d4e0ef39ca3a36ff19b40f47f266a639e9cccf5f013ba19f9b784d5848ba`.
Helper SHA256:
`4e480e2d2f62e87b2260516c83afc2f7aae741b36ef8680578735f1d91233afb`.
Browser verifier SHA256:
`57a1e61f63b1447bcd20b6e11a11301cf760cb2f12f89a04585ce0de3a99021b`.

Before any future authorized execution, verify the outer manifest hash and every
entry with sha256sum -c DEPLOYMENT_SHA256SUMS. Use a new staging directory; never
reuse the consumed ATTEMPT_USED. Inner artifact manifest is unchanged a75bbd94….
Original three rollback hashes remain in ATLAS_OBJECT_TARGET_INSTALL_20261030.md.
All seven additional destinations must be absent. Failure restores those three
and removes only matching additions, followed by only the approved web rollback
restart. Inference remains false; no test-start requests are permitted.

## Remaining gate

Do not request an immediate deployment retry: whole-Jetson rejection is real and
process attribution remains unavailable. Further analysis should use existing
historical process evidence if timestamp-aligned samples exist. Any new restart
capture needs a separately reviewed/approved bounded plan; it must not be disguised
as another installation. No hardware success or CPU fix is claimed by these tests.
