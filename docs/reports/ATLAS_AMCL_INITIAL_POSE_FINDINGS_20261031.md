# Separate AMCL initial-pose investigation — 2026-10-31

Read-only existing journals/verdict/configuration and repository source reviewed.
No ROS node or pose publication, service restart, camera activation or movement.
Recovery remains STOPPED; CPU investigation remains stopped/root cause UNKNOWN.

## Confirmed warning chain (IST)

- Oct30 16:47:46: map_server loads atlas_latest.yaml and atlas_latest.pgm.
- 16:47:47: map_server activates; AMCL receives a232x220 map at0.050m/pixel;
  AMCL activates. Thus this is NOT evidence of a missing/unreadable map file.
- 16:48:37: startup seeder explicitly reports LOCALIZATION UNKNOWN, AMCL NOT
  seeded because two places fit almost equally. It advises checking the current
  named place before any seed.
- Oct31 09:03:40–53 and later saved journal: AMCL requests an initial pose;
  Nav2 costmap waits for the map frame/transform. These predate Recovery restart.

Persisted verdict boot_id matches the current boot. Mode=verify, pose=null,
navigation_authorized=false. Three attempts were UNKNOWN; margins0.000,0.008,
0.004. Final top fits0.935 and0.931, margin0.004. Repository verifier requires
margin>=0.06; no threshold changed. Saved verdict map SHA256:
d957f0fe3b8b48166751ef0226ba5f7abdd5454e6f44fac4c9e7b430f00c45e4.
Raw scan/pose evidence retained privately in work/localization-verdict-review-20261031.json.

## Interpretation and limits

Immediate cause is an intentionally withheld initial pose after ambiguous scan-to-
map matching. Seeder returns before creating the initial-pose publisher/client
when pose is None. AMCL source reference1.1.20 explicitly refuses pose output when
initial_pose_is_known_ is false; repository tf_broadcast remains true. This explains
why a valid loaded occupancy map does not provide a usable map->odom TF chain.
No indication that restarting Recovery or map_server would resolve ambiguity.

Why two places match is still UNKNOWN: repetitive geometry, scan occlusion, changed
surroundings, wrong map or other geometric factors are not distinguished by scores.
No claim that one candidate is the correct physical pose. Process-active does not
mean localization ready. This finding is separate from the86.93% CPU incident and
is not proof of its cause.

## Focused checks

Existing ambiguity test PASS. Existing seeder source-order test ERROR: it searches
for obsolete text pose_client.call_async, now wrapped by checkpoint_observer.call.
This is stale test implementation, not observed runtime pose publication. Manual
source review confirms UNKNOWN return precedes publisher/client creation and the
observer call. No runtime patch or unrelated test rewrite made. Do not call the
entire localization test suite PASS.

## Smallest safe next step (not executed)

Review saved scan/map evidence and obtain an independently confirmed current named
place/map identity before proposing the existing --verify-place workflow. Keep
uniqueness/fit thresholds and navigation authorization unchanged. Any actual pose
publication or stationary verification requires separate approval. Do not blindly
seed the saved home pose, inject a static map transform, relax margins or restart
services to silence warnings. Localization issue remains OPEN; immediate cause
confirmed, physical disambiguation unresolved. All safety limits unchanged.