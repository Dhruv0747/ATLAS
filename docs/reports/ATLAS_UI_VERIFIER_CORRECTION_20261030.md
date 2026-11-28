# UI verification correction only — GO, execution not approved

No application or HTML modification. The six-panel candidate and targeted patch
from d39c867 remain byte-for-byte unchanged. No deployment, camera activation,
inference, restart or rover control operation was performed.

## Correction

`verify_ui_stopped.cjs` accepts the two existing UI presentations `Camera off` and
`Stopped safely`. Both require fresh GET `/api/vision3d/summary` before AND after
the rendered-state check, with state exactly OFF and driver_stopped exactly true.
API errors, missing/malformed values, stale HTTP Age, timeouts and active camera
states fail closed. Requests are bounded to two seconds; UI wait to five seconds.
No reliance on text alone and no camera lease renewal through the summary endpoint.

`verify_feature_ui_live.cjs` is the corrected PC-side deployment verifier. It also
checks the exact served candidate hash, six cards, 24 disabled buttons, material.css,
previews, distance element, Home link, layout overflow and page errors at four
widths. It writes PASS/FAIL evidence for the existing single-use transaction;
it does not deploy. Failure still triggers exact-byte rollback.

## Tests

Focused helper tests PASS: both labels, two authoritative reads, and rejection of
ACTIVE/missing/malformed/false/nonboolean driver state, cached or unavailable API.
Offline browser tests PASS for both label scenarios at 1440, 768, 390 and 320 px
(8 candidate viewport checks plus corresponding original-page comparisons).
Original navigation/control IDs unchanged, all feature controls disabled, no page
errors, no non-GET requests, no overflow. Edge/Chromium only; Safari/Firefox remain
untested. All browser-test network responses were isolated fixtures.

Live read-only rollback check: HTML and previous rollback.html both SHA256
`1511d33f060c450a3afc0c120711f1da18587f5f37f9e0796fad7d577bcddb48`.
Web PID2098, active, NRestarts0. Previous failed attempt evidence preserved.

## One prepared package

Local sibling directory `vision-ui-corrected-verifier-review` contains original,
candidate, targeted patch, unchanged one-attempt deployment wrapper, corrected
live verifier, shared verification helper and SHA256SUMS. It has NOT been staged
on Jetson. No prior ATTEMPT_USED marker or browser PASS acknowledgement is copied.

Manifest SHA256:
`b4032ccca08937d3bc6be73b1b52a80626ae4354d240bb4cd391431843e713f8`.
Unchanged candidate SHA256:
`6d12362130e53fc6bb545ddba51100bf20a957e2f1ea7284a88ea9743c17ea57`.

After separate approval only: stage into a NEW directory, verify SHA256SUMS and
fresh live/safety state, run the single-use wrapper once, run corrected PC verifier
against the existing Lab URL and deliver its new acknowledgement. The existing
90-second validation timeout rolls back if acknowledgement is absent or failed.
Never reuse the old attempt command or old browser acknowledgement. All existing
rollback instructions apply. Only the approved HTML may change; no restart.

GO for one separately approved UI-only deployment. Request approval for this
unchanged HTML candidate with corrected authoritative verification. Keep all new
feature controls disabled. URL remains http://192.168.1.16:8088/v2/vision3d .
