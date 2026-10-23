# Shared lightweight glass UI — candidate, not deployed

## Approved installation attempt — 23 October

Owner approved installing the white-glass UI on all active pages without restart,
camera start or motion. All ten actual live HTML pages match the pre-theme baseline
after newline normalization. The installer preserves the exact live bytes and adds
only one stylesheet link, rather than replacing live pages with repository copies.
Candidate CSS SHA256:
`ea6a213b8a7b5aa5f4777af64259a75589799ebd151e39acf4723fc6fb6368d5`.
Exact baseline manifest SHA256:
`26a1cb668cf6b6a95d746ccad6276b725f82ac713b4319e36879a1c282f82a4c`.

**ABORTED BEFORE INSTALLATION:** first fresh 1-second CPU sample was
76.0942760942761%, above the preserved75% limit. Resource check exited before
RAM/temperature/policy sampling; do not report those as freshly passed. Astra-OFF
check and protected-service active check passed first. No retry performed.
No HTML or CSS was installed; all ten live HTML hashes remain equal to the
manifest, material.css remains absent and web PID1973/restarts0 is unchanged.
No service restart, reboot, permission/network change, recording or movement.

Evidence directory (result only; preflight stopped before production backup):
`/home/jetson/project-atlas-migration/white-glass-20261023/white-glass-backup-litstex5/`.
The staging directory retains installer, CSS and exact manifest. Four offline
installer tests cover byte-preserving edits, duplicate/ambiguous-head rejection,
atomic write/restore and CSS hash pin. All ten copied live files also passed
offline patch/duplicate-rejection rehearsal.

Next: a fresh guarded attempt after resource headroom is available. No threshold
change is proposed. Before/after CPU comparison was not reached; no CPU saving or
live-theme quality claim is supported by this aborted attempt. The production UI
remains its previous theme.

Owner requested a consistent glassmorphism, skeuomorphic and neumorphic style,
then requested blur and a stronger glass appearance without invisible panels.

## Scope

One shared `project_atlas/web/v2/material.css` layer loads last on all ten V2 HTML
pages: Home, classic console, mapping, commissioning, Wi-Fi, camera, LiDAR,
motor test lab, FlySky lab and 3D Vision Lab. These are the active default dashboard
routes. Archived V1/disabled dashboard sources are deliberately not changed.

Owner's follow-up switches the candidate to white glass with a faint, static ATLAS
logo watermark using the existing local 512px WebP (22,474 bytes). Text, controls
and status surfaces are adapted for the light background; E-STOP remains red.
Tinted panels use 68% opacity (32% transparency), subtle edge highlights and small
static shadows. Buttons are raised, fields recessed. A single direct-body header
may use 6px backdrop blur; panels and docks never blur live video/map/3D pixels.
Lite mode and reduced-transparency preferences remove blur. Red E-STOP, semantic
status colours, disabled controls and visible keyboard-focus rings are retained.

No production Python/JavaScript, IDs, event handlers, API paths, polling rates,
steering settings, sensor processing, networking, safety limits or ROS settings
changed. The only HTML change is the final stylesheet link, plus line endings/EOF
normalization where applicable. Existing classic-preservation test now strips
that exact link and normalizes CRLF before checking the original archived SHA.

## Resource claims

The new file is under 8.5KB, shared across pages, with no external assets or runtime
JavaScript. It removes panel/dock backdrop filters instead of adding nested blur.
The effects are rendered by the viewing device. A browser running on the Jetson
would still consume Jetson resources. No measured browser CPU/GPU or whole-Jetson
savings are claimed; populated live UI performance remains a deployment gate.

## Tests

60 Python tests passed: theme contract5, static routes7, default routes8,
Stage31 UI17, E-STOP safety12, idle camera11. The separate Stage17B Node steering
UI check passed. Initial Windows runs lacked cv2/POSIX APIs; relevant suites were
rerun successfully in existing WSL Ubuntu22.04. A newline-only preservation failure
was corrected without replacing the archived expected checksum.

Browser visual review, including white-glass follow-up: narrow-window Home and Vision Lab previews retain readable
glass surfaces and prominent E-STOP. This is not an exhaustive desktop/mobile or
live-data accessibility/performance certification. Production scripts were blocked
by CSP in the local preview, so no camera requests, API polling or control commands
could occur. `preview_material_ui.py` serves static files only on loopback8767;
it is a local review aid, not a production component.

## Deployment and rollback

NOT installed on Jetson. Before installation, owner approval and fresh stopped
safety checks are required. Hash and back up the ten actual live HTML files;
compare them to the reviewed baseline, preserving developer changes. Install CSS
first, then only the matching HTML link edits. The existing static asset handler
reads files per request; no service restart should be necessary. Do not deploy
the preview server or tests. Validate routes and UI without starting cameras or
issuing movement. Restore saved HTML and CSS on visual/functional regression;
reload the browser, not rover services. Keep all runtime limits unchanged.
