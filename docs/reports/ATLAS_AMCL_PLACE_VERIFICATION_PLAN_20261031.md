# AMCL ambiguity and manual verification plan — 2026-10-31

No live localization workflow executed. No pose publication, service restart,
camera/inference, movement or safety change. Recovery remains STOPPED; CPU incident
OPEN and separate. This work is saved-evidence analysis plus a test-only correction.

## Evidence comparison

Saved final scan:360 beams,294 valid endpoints,246 held-out beams. Reused existing
verifier math and copied map files read-only for offline scoring; no global search
or new scan. Map YAML SHA256 matches recorded d957f0fe3b8b48166751ef0226ba5f7abdd5454e6f44fac4c9e7b430f00c45e4.
Image SHA256 now4beb26d5a9990db537df53ba71404d549f88f717d72ca59fc03e0b72a3684a1e;
original verdict recorded YAML hash only, so historical image identity is not
independently guaranteed. However replay reproduces both rounded recorded scores.

At unchanged0.15m wall tolerance, candidates fit230/246 and229/246 held-out beams
(0.934959 and0.930894).213 beams match at BOTH placements;17 distinguish the first,
16 distinguish the second. Thus just one net beam separates these poses. Median
valid range0.46m: nearby geometry dominates this scan. This establishes geometric
aliasing for the recorded endpoint score; it does not prove its physical cause
(furniture/occlusion/repeated room layout) or which pose is true. No threshold
change is warranted. Uniqueness margin remains0.06, minimum fit0.93.

Only the second candidate is inside the existing Dhruv Room region. The first is
outside; its named room is not established. Do not infer actual location from this.
Owner independently confirmed current room: DHRUV ROOM. Heading relative to a fixed
landmark and whether moved/lifted since Oct30 remain pending. Saved scan cannot be
assumed current without that information. No exact pose selected or published.

## Existing --verify-place behavior reviewed, NOT executed

Repository place_regions.json defines only Dhruv Room, tied to the accepted YAML
hash. --verify-place restricts the search to that operator-confirmed region; it
retains fit/margin requirements and multi-attempt agreement checks, never blindly
loads the saved home pose. Map mismatch/unknown region reject. Region restriction
must rerun search: deleting the other saved candidate does NOT establish VERIFIED.

--verify-place alone CAN apply a pose via /set_initial_pose or /initialpose fallback.
It is therefore not a read-only command. Adding --dry-run returns before pose
publisher/client creation and verdict writes, but still creates a ROS node and
collects current LiDAR/odom/TF; it needs separate live authorization. Do not run it
under this offline approval. InitializationObserver can publish diagnostic events
if ATLAS_CHECKPOINT_EVENTS=1; ensure this remains disabled in a read-only proposal.

The internal60s search budget is checked between attempts, not a strict wall-clock
kill bound. Any approved live procedure must use existing external supervision,
not assume that constant alone guarantees a bounded run. No new wrapper built.

## Test-only correction (separate commit ed88556)

Updated stale source-order assertions from pose_client.call_async to current
checkpoint_observer.call(pose_client, request,...). Runtime sources unchanged.
Five focused existing tests PASS: UNKNOWN exits before seeding; region validation,
accepted-map binding, mutual exclusion/no seed overwrite, map mismatch rejection.
This is offline validation, not a physical localization success.

## Shortest safe procedure / approval gates

1. Owner-confirmed Dhruv Room is recorded. Obtain front-facing landmark and movement/
   lifting history. Keep stationary; do not move ATLAS to fit a saved candidate.
2. Review current map/region identity and independently confirmed placement. If
   moved, use old scan only as historical evidence, never as a current initial pose.
3. After separate approval, propose ONLY existing --verify-place with --dry-run,
   fresh E-STOP/zero/stationary/freshness and75%CPU/80%RAM/<70C supervision, strict
   external duration and no retries. No Recovery restart is part of this process.
4. UNKNOWN or any guard failure means STOP; preserve evidence. No lowered margin,
   fabricated transform, default home pose or autonomous navigation.
5. A VERIFIED dry run still needs owner review of pose/heading and separate approval
   before any actual pose application. Then verify AMCL pose/map->odom freshness and
   geometric agreement; a service response alone is not localization acceptance.

Status: room known, exact pose/heading unverified. No live step approved or run.