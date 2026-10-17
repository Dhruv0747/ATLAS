#!/usr/bin/env python3
"""Additive, idempotent patch of the LIVE atlas_status_web.py and atlas_web_v2.py for the FlySky Remote Test Lab
(usage: insert_hooks.py <project_atlas dir>).  Inserts one import, two hook lines and one page entry.
Every anchor must match exactly once or nothing is written.  The existing Test Lab hooks are required and untouched."""
import sys
from pathlib import Path

root = Path(sys.argv[1])
sw, v2 = root / 'scripts/atlas_status_web.py', root / 'scripts/atlas_web_v2.py'
s, w = sw.read_text(), v2.read_text()
imp = "import atlas_testlab_web   # Motor & Encoder Test Lab (additive; own node, read-only unless the lifted gates are open)\n"
a = "        if atlas_testlab_web.serve(self, ROS):\n            return\n"
b = "        if atlas_testlab_web.serve(self, ROS, post=True):\n            return\n"
page_old = "'testlab': 'testlab.html'}"
page_new = "'testlab': 'testlab.html', 'flysky-testlab': 'flysky-testlab.html'}"
for text, anchor in ((s, imp), (s, a), (s, b), (w, page_old)):
    if text.count(anchor) != 1:
        sys.exit('REFUSE: anchor not found exactly once: %r' % anchor[:70])
if 'atlas_flysky_web' in s or 'flysky' in w:
    sys.exit('REFUSE: already patched')
s = s.replace(imp, imp + "import atlas_flysky_web   # FlySky Remote Test Lab (additive; read-only, lazy subscriber, no publishers)\n", 1)
s = s.replace(a, a + "        if atlas_flysky_web.serve(self, ROS):\n            return\n", 1)
s = s.replace(b, b + "        if atlas_flysky_web.serve(self, ROS, post=True):\n            return\n", 1)
w = w.replace(page_old, page_new, 1)
compile(s, str(sw), 'exec'); compile(w, str(v2), 'exec')
sw.write_text(s); v2.write_text(w)
print('patched', sw.name, v2.name)
