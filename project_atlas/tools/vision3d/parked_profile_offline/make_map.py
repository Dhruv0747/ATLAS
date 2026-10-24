"""Synthetic 20 x 20 m free map with border walls (0.05 m/px). Not an ATLAS map."""
import sys
from pathlib import Path
out = Path(sys.argv[1]); out.mkdir(parents=True, exist_ok=True); W = H = 400
px = bytearray()
for y in range(H):
    for x in range(W):
        px.append(0 if x < 4 or y < 4 or x >= W - 4 or y >= H - 4 else 254)
(out / 'synthetic.pgm').write_bytes(b'P5\n%d %d\n255\n' % (W, H) + bytes(px))
(out / 'synthetic.yaml').write_text('image: synthetic.pgm\nresolution: 0.05\norigin: [0.0, 0.0, 0.0]\nnegate: 0\noccupied_thresh: 0.65\nfree_thresh: 0.196\nmode: trinary\n')
print(out / 'synthetic.yaml')
