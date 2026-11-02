# Monitoring CPU rejection evidence — 2026-11-02

Monitoring recovery remains BLOCKED. The m2-postboot-20261102 attempt is CONSUMED.
No replacement archive or execution command is prepared by this change.

## Confirmed observations

Owner-supplied result reports FAIL, cleanup VERIFIED, reason `CPU limit`, evidence `{}`.
The transaction ran 8.229 seconds. Original M2 FAULT SHA256 remains
`fc5479c96fd42ee003a565b0ccb7e63caaf9d29c43a383eff5291a3c938302fd`.
The supplied nft output contains no tables. These are retained results, not a new live audit.

The unprotected admission path reads /proc/stat, checks an increasing total counter
and a 0.8–1.5-second interval, calculates CPU, then calls guard.validate. CPU rejection
occurs before returning the observation; samples.jsonl only saves accepted observations.
Unlike guard.observe, this path did not populate guard.EVIDENCE. This is the confirmed
cause of the empty failure evidence. The enclosing failure writer and cleanup were reached.

The computed value came from a new counter read, not reuse of a previous CPU percentage.
Its magnitude, raw counters, transient versus sustained load, process contributors and
physical overload cause remain UNKNOWN. The predicate can reject nonfinite/out-of-range
values as well as over-limit values. No numerical peak can be recovered from this output.
The historical M2 cause is separate; owner-reported wheel handling does not rewrite it.

## Scoped offline correction

Admission clears old evidence and records CPU, validity, monotonic sample timestamp,
interval, age, 75% threshold, required comparison and rejection stage before validation.
Missing/nonfinite values remain rejected and serialize as null, never zero. Finally records
age on rejection. The existing transaction strict-limit path retains its current sample
metadata at exactly 75%. Existing guard, safety decisions, archive/reset, firewall and
rollback logic are unchanged. Source sampler SHA pin updated; consumed archives unchanged.

Focused native Linux checks: 13 passed, 49 unrelated cases deselected. Covered over-limit,
negative/nonfinite, missing counters, invalid interval, exact 75%, just-below, JSON evidence
and source hash pin; existing strict CPU/RAM boundaries also pass. No physical acceptance.

Next safe action: review this evidence-only correction. Any future package must have a
new single-use identity, reviewed hashes and separate execution approval after fresh safety
checks. Do not reuse the consumed transaction. No live restart or latch reset authorized.
