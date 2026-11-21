# Six-feature UI-only deployment preparation

Verdict: GO for separately approved single-file UI deployment, subject to the same
fresh live hash at execution. No deployment performed. No restart required.
Source candidate a5de48c; this preparation deliberately excludes its inference
backend, feature JavaScript polling, source-stamp edit and execution configuration.

## Exact live comparison

Read-only SSH verified active server `/home/jetson/project_atlas/scripts/atlas_status_web.py`.
The live HTML has `material.css`, absent from the repository candidate. This patch
preserves it and every original byte. Live vision3d.js differs by the repository's
new source-stamp assignment: leave it untouched. Live vision3d.css, glass.css and
base.css match normalized repository content. Backend API additions are excluded.

| File | Live SHA256 (unchanged at final recheck) |
|---|---|
| web/v2/vision3d.html | 1511d33f060c450a3afc0c120711f1da18587f5f37f9e0796fad7d577bcddb48 |
| web/v2/vision3d.js | 82d846cd09570d53ef984adc97bf51bed4be4d0ab629bf33b2386544e9d9084e |
| web/v2/vision3d.css | 69af9900d408bdbc60b3a717d02d9ad5dfece80f1e5165bead0a28c61660a510 |
| scripts/atlas_vision3d_web.py | 2551d6578aa9429ac8f4fd5ff35f2c16a185c3cd027fafc563b7fff339857190 |

`rover-status-web`: PID 2098 before/after, active, final NRestarts=0.
No camera API, inference, ROS participant, service restart or Jetson file write
was invoked. Existing static handler reads HTML per request, no-cache; changing
this one HTML file therefore does not require a Python/web restart.

## Patch and status semantics

`prepare_feature_ui.py` rejects any other baseline hash. It inserts one scoped
static section before `</main>`, containing six cards and 24 disabled buttons.
No script, handler, fetch, timer, link or new subscription is added. Scoped CSS
reuses existing buttons/white-glass surfaces without adding backdrop blur.
Existing camera controls, preview, distance measurement, navigation and E-STOP
are unchanged. Status text is explicitly dated implementation status, not health.

Face and gesture: NOT INSTALLED. Body, target, object and mapping: UNAVAILABLE.
Person-box tracking is not skeletal pose; model presence is not Astra validation;
distance preview is not calibrated mapping. No test is claimed VERIFIED.

Prepared package contains original.html, candidate.html, targeted.patch,
SHA256SUMS, manifest.json. Local directory: `../vision-ui-only-review` relative
to the worktree. Candidate SHA256:
`6d12362130e53fc6bb545ddba51100bf20a957e2f1ea7284a88ea9743c17ea57`.
Patch SHA256:
`e099729614e8ec951b3507f6351a279e12eebbdfec4a3c9ca291d1d286502833`.
Exact inverse restored the original bytes and hash. Do not use the older full
repository page or install any feature backend for this UI-only change.

## Focused validation

* Three patch tests PASS: unknown-baseline rejection, static-only six-panel/24-
  disabled-control assertions, changed-rollback rejection.
* Exact original-to-candidate-to-original byte comparison PASS.
* Offline Edge/Chromium browser checks PASS at 1440, 768, 390 and 320 px widths.
  Original links/control IDs unchanged; material.css retained; no horizontal
  overflow; no page errors or non-GET requests. All requests intercepted locally.
* Mobile screenshot visually inspected. Existing fixed E-STOP dock retained.
* Firefox, Safari and real phone hardware NOT tested. Basic semantic HTML and
  responsive CSS used; no new JavaScript/browser API dependency.
* Existing preview pipelines were not rerun. Their HTML/JS/CSS are preserved,
  rather than claiming a new real-camera regression pass.

## Proposed execution and exact rollback (DO NOT RUN before approval)

After separately approved package staging, use this directory:
`/home/jetson/project-atlas-migration/vision-ui-only-20261030`.
The following is preparation, not authorization:

```sh
set -eu
cd /home/jetson/project-atlas-migration/vision-ui-only-20261030
sha256sum -c SHA256SUMS
live=/home/jetson/project_atlas/web/v2/vision3d.html
test ! -L "$live"
test "$(sha256sum "$live" | cut -d ' ' -f1)" = 1511d33f060c450a3afc0c120711f1da18587f5f37f9e0796fad7d577bcddb48
test ! -e rollback
umask 077
mkdir rollback
cp -p "$live" rollback/vision3d.html
cmp "$live" rollback/vision3d.html
tmp=$(mktemp /home/jetson/project_atlas/web/v2/.vision3d-ui.XXXXXX)
trap 'rm -f -- "$tmp"' EXIT
cp -p "$live" "$tmp"
cat candidate.html > "$tmp"
test "$(sha256sum "$tmp" | cut -d ' ' -f1)" = 6d12362130e53fc6bb545ddba51100bf20a957e2f1ea7284a88ea9743c17ea57
mv -fT "$tmp" "$live"
sha256sum "$live"
```

Then inspect `/v2/vision3d` without pressing any camera/control button. Verify six
static cards, original navigation and layout, unchanged service PID and unchanged
protected hashes. On validation failure restore only this HTML:

```sh
set -eu
cd /home/jetson/project-atlas-migration/vision-ui-only-20261030
live=/home/jetson/project_atlas/web/v2/vision3d.html
test ! -L "$live"
test "$(sha256sum "$live" | cut -d ' ' -f1)" = 6d12362130e53fc6bb545ddba51100bf20a957e2f1ea7284a88ea9743c17ea57
test "$(sha256sum rollback/vision3d.html | cut -d ' ' -f1)" = 1511d33f060c450a3afc0c120711f1da18587f5f37f9e0796fad7d577bcddb48
tmp=$(mktemp /home/jetson/project_atlas/web/v2/.vision3d-rollback.XXXXXX)
trap 'rm -f -- "$tmp"' EXIT
cp -p rollback/vision3d.html "$tmp"
mv -fT "$tmp" "$live"
sha256sum "$live"
```

If live hash changed, STOP rather than overwriting another change. Keep backups
and evidence. No systemctl, camera, model, controller or firmware operation needed.

## Approval requested

Approve one UI-only installation of the exact candidate hash above into the live
Vision Lab HTML, with verified backup and rollback. Keep all new feature controls
disabled. No camera start, inference, tracking, movement or service restart.
Target URL: http://192.168.1.16:8088/v2/vision3d (new section not deployed yet).
