#!/usr/bin/env python3
"""Additive, idempotent patch of the LIVE atlas_status_web.py and atlas_web_v2.py (usage: insert_hooks.py <project_atlas dir>).

The repo copy of atlas_status_web.py contains other, undeployed work (single-person steering), so it must NOT be copied
over the live file.  This inserts only the Test Lab import and two hook lines, and the 'testlab' V2 page entry.
Every anchor must match exactly once or nothing is written."""
import sys
from pathlib import Path

root = Path(sys.argv[1])
sw, v2 = root / 'scripts/atlas_status_web.py', root / 'scripts/atlas_web_v2.py'
s, w = sw.read_text(), v2.read_text()
imp = "import atlas_location_check_web\n"
a = "        if atlas_location_check_web.serve(self, ROS):\n            return\n"
b = "        if atlas_location_check_web.serve(self, ROS, post=True):\n            return\n"
page_old, page_new = "'lidar': 'lidar.html'}", "'lidar': 'lidar.html', 'testlab': 'testlab.html'}"
for text, anchor in ((s, imp), (s, a), (s, b), (w, page_old)):
    if text.count(anchor) != 1:
        sys.exit('REFUSE: anchor not found exactly once: %r' % anchor[:60])
if 'atlas_testlab_web' in s or 'testlab' in w:
    sys.exit('REFUSE: already patched')
s = s.replace(imp, imp + "import atlas_testlab_web   # Motor & Encoder Test Lab (additive; own node, read-only unless the lifted gates are open)\n", 1)
s = s.replace(a, a + "        if atlas_testlab_web.serve(self, ROS):\n            return\n", 1)
s = s.replace(b, b + "        if atlas_testlab_web.serve(self, ROS, post=True):\n            return\n", 1)
w = w.replace(page_old, page_new, 1)
compile(s, str(sw), 'exec'); compile(w, str(v2), 'exec')
sw.write_text(s); v2.write_text(w)
print('patched', sw.name, v2.name)
