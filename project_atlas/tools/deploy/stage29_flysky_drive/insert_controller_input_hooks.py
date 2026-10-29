#!/usr/bin/env python3
"""Stage 29 dashboard: additive hooks in the LIVE atlas_status_web.py (A3, sha 983024c3) for
atlas_controller_input_web (read-only live Xbox input for the FlySky Driving page). Anchor-exact; refuses on mismatch.

Adds exactly: one import and one GET route hook. No subscription, client or publisher is added to the dashboard's
own node (the module owns a separate lazy read-only node). POST is not hooked.
Usage: insert_controller_input_hooks.py <input atlas_status_web.py> <output>
"""
import sys

MARK = '# ATLAS Stage 29 controller input view'
EDITS = [
    ("import atlas_manual_controller_web   # ATLAS Stage 29 manual controller: Xbox/FlySky selection + FlySky drive status\n",
     "import atlas_manual_controller_web   # ATLAS Stage 29 manual controller: Xbox/FlySky selection + FlySky drive status\n"
     "import atlas_controller_input_web   # ATLAS Stage 29 controller input view: read-only live Xbox /joy for the page\n"),
    ("        if atlas_manual_controller_web.serve(self, ROS):   # ATLAS Stage 29 manual controller\n            return\n",
     "        if atlas_manual_controller_web.serve(self, ROS):   # ATLAS Stage 29 manual controller\n            return\n"
     "        if atlas_controller_input_web.serve(self, ROS):   # ATLAS Stage 29 controller input view (GET, read only)\n            return\n"),
]


def apply(text: str) -> str:
    if MARK in text:
        raise SystemExit('refused: already patched')
    for old, new in EDITS:
        n = text.count(old)
        if n != 1:
            raise SystemExit('refused: anchor found %d times: %r' % (n, old[:70]))
        if not new.startswith(old):
            raise SystemExit('refused: edit is not additive')
        text = text.replace(old, new, 1)
    return text


if __name__ == '__main__':
    src, dst = sys.argv[1:3]
    out = apply(open(src, encoding='utf-8').read())
    compile(out, dst, 'exec')
    open(dst, 'w', encoding='utf-8').write(out)
    print('wrote', dst)
