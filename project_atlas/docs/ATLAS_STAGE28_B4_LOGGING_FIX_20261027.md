# B4 Windows logging correction — offline PASS

Owner confirmed transmitter OFF and authorized offline correction only. No COM port, board reset, flash command, transmitter operation or Jetson service was used in this work. Original failed evidence directory is preserved.

## Cause and correction

Confirmed original failure: Windows denied replacing latest.json, causing the receive-only monitor to abort and close COM26. It left an older latest.json saying MONITORING. The exact process/handle responsible for the original access denial is unknown. A native Windows test reproduces the old replacement failure by holding the destination open without delete-sharing; this demonstrates the failure mechanism, not the identity of the original competing process.

New PC tooling writes numbered immutable status snapshots. Each uses an exclusive pending file, flush/fsync, then rename to a new filename. It never replaces a file a reader may already have open. The session remains capped at900seconds with roughly0.5second status cadence (about1800 snapshots); no historical evidence is deleted. Reads ignore pending files, use the newest committed snapshot, prioritize legacy terminal result.json and reject missing/corrupt/stale data. Live status requires a true drive-disabled flag and a heartbeat no older than2seconds. It does not mean receiver frames are fresh: ever/fresh/age and channel fields remain separate.

Real write/rename/disk errors still abort. Serial closes before terminal evidence is attempted. If even terminal evidence cannot be saved, the error is printed and raised; the last heartbeat expires within2seconds. Persistent storage failure cannot guarantee a final disk record. No retry of serial connection or capture is implemented. An exclusive attempt marker prevents rerunning the same session directory. New --run-approved-session and --evidence-dir arguments require deliberate invocation; approval must be obtained separately.

Files:
- tools/flysky/passive_evidence.py — snapshot writer and fail-closed status reader.
- tools/flysky/passive_sbus_monitor.py — existing monitor adapted to that writer and portable repository paths; remains receive-only.
- tests/test_stage28_b4_logging.py — Windows/file-error/fake-serial regression tests.

## Tests

Native Windows Python3.13: **12 passed**, including real Win32 file-sharing denial, old-method failure/new-method success, live/stale/future timestamps, abort superseding live, corrupt/missing/pending evidence, fsync failure, collision protection, simulated clean stop, checksum abort, logging abort closing serial, and duplicate-attempt rejection. Serial is replaced with a fake object whose write method raises; no real hardware is opened.

Existing WSL firmware/RC/hooks/release regressions: **32 passed**. Total44 passed. A test fixture initially reused a deliberately incomplete pending filename; corrected the fixture to distinguish abandoned evidence from a fresh publication. No production safety checks were weakened to pass tests.

## Status and next gate

Offline correction ready for review; NOT live validated. CH1–CH10 and signal-loss behavior remain unverified. The corrected reader must be used to inspect live state instead of trusting a saved MONITORING string. Another B4 session requires separate owner approval, fresh isolation/readiness confirmation and the usual transmitter-ON instruction after monitoring is verified. No live retry performed here.

Rollback is PC-only: leave these new tools unused or revert this commit. No deployed firmware, white-glass UI, voice feature, safety limit or board configuration changed. The original failed monitor/evidence remains untouched and must not be reused for a new attempt.
