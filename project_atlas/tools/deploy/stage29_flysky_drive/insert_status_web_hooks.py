#!/usr/bin/env python3
"""Stage 29: additive hooks in atlas_status_web.py for atlas_manual_controller_web (anchor-exact; refuses on mismatch).

Adds: one import; one read-only subscription (/atlas/flysky/drive_status) and two Trigger clients
(/atlas/manual_controller/select_xbox|select_flysky) on the existing node; the GET and POST route hooks.
Nothing else changes. Usage: insert_status_web_hooks.py <input atlas_status_web.py> <output>
"""
import sys

MARK = '# ATLAS Stage 29 manual controller'
EDITS = [
    ("import atlas_flysky_web   # FlySky Remote Test Lab (additive; read-only, lazy subscriber, no publishers)\n",
     "import atlas_flysky_web   # FlySky Remote Test Lab (additive; read-only, lazy subscriber, no publishers)\n"
     "import atlas_manual_controller_web   # ATLAS Stage 29 manual controller: Xbox/FlySky selection + FlySky drive status\n"),
    ("            self.node.create_subscription(String, '/atlas/control_policy', lambda m: self._set('control_policy', m.data), 10)\n",
     "            self.node.create_subscription(String, '/atlas/control_policy', lambda m: self._set('control_policy', m.data), 10)\n"
     "            # ATLAS Stage 29 manual controller: FlySky drive status (read-only) and the mux selection services.\n"
     "            self.node.create_subscription(String, '/atlas/flysky/drive_status', lambda m: self._set('flysky_drive', m.data), 10)\n"
     "            self.manual_controller_clients = {t: self.node.create_client(Trigger, '/atlas/manual_controller/select_' + t.lower())\n"
     "                                              for t in ('XBOX', 'FLYSKY')}\n"),
    ("        if atlas_flysky_web.serve(self, ROS):\n            return\n",
     "        if atlas_flysky_web.serve(self, ROS):\n            return\n"
     "        if atlas_manual_controller_web.serve(self, ROS):   # ATLAS Stage 29 manual controller\n            return\n"),
    ("        if atlas_flysky_web.serve(self, ROS, post=True):\n            return\n",
     "        if atlas_flysky_web.serve(self, ROS, post=True):\n            return\n"
     "        if atlas_manual_controller_web.serve(self, ROS, post=True):   # ATLAS Stage 29 manual controller\n            return\n"),
]


def apply(text: str) -> str:
    if MARK in text:
        raise SystemExit('refused: already patched')
    for old, new in EDITS:
        n = text.count(old)
        if n != 1:
            raise SystemExit('refused: anchor found %d times: %r' % (n, old[:70]))
        if old not in new:
            raise SystemExit('refused: edit is not additive')
        text = text.replace(old, new, 1)
    return text


if __name__ == '__main__':
    src, dst = sys.argv[1:3]
    out = apply(open(src, encoding='utf-8').read())
    compile(out, dst, 'exec')
    open(dst, 'w', encoding='utf-8').write(out)
    print('wrote', dst)
