import sys; sys.path.insert(0, '.')
from common import *
from PIL import Image, ImageDraw, ImageFont
BOX = (-1.6, 7.6, -3.6, 1.8)   # x0,x1,y0,y1 local region
def load_raw(m, path):
    from PIL import Image
    m['raw'] = np.array(Image.open(path))[::-1].copy(); return m

def render(m, path, S=10, overlays=(), box=BOX, title=None):
    x0, x1, y0, y1 = box; res, ox, oy = m['res'], m['origin'][0], m['origin'][1]
    c0, c1 = int((x0 - ox) / res), int((x1 - ox) / res); r0, r1 = int((y0 - oy) / res), int((y1 - oy) / res)
    raw = m.get('raw')
    if raw is None:
        occ = m['occupied'][r0:r1, c0:c1]; free = m['free'][r0:r1, c0:c1]
        img = np.where(occ, 20, np.where(free, 245, 175)).astype(np.uint8)[::-1]
    else:
        sub = raw[r0:r1, c0:c1]; img = np.where(sub < 50, 20, np.where(sub > 250, 245, 190)).astype(np.uint8)[::-1]
    im = Image.fromarray(img).resize((img.shape[1] * S, img.shape[0] * S), Image.NEAREST).convert('RGB'); d = ImageDraw.Draw(im)
    H = img.shape[0] * S
    px = lambda x, y: ((x - (ox + c0 * res)) / res * S, H - (y - (oy + r0 * res)) / res * S)
    for gx in np.arange(math.ceil(x0), x1, 1.0):
        d.line([px(gx, y0), px(gx, y1)], fill=(150, 190, 255), width=1); d.text((px(gx, y0)[0] + 2, H - 14), f'x={gx:.0f}', fill=(0, 60, 200))
    for gy in np.arange(math.ceil(y0), y1, 1.0):
        d.line([px(x0, gy), px(x1, gy)], fill=(150, 190, 255), width=1); d.text((2, px(x0, gy)[1] + 2), f'y={gy:.0f}', fill=(0, 60, 200))
    for kind, data, color in overlays:
        if kind == 'pts':
            for x, y in data:
                X, Y = px(x, y); d.rectangle([X - 1.5, Y - 1.5, X + 1.5, Y + 1.5], fill=color)
        elif kind == 'pose':
            name, (x, y, a) = data; X, Y = px(x, y)
            d.ellipse([X - 7, Y - 7, X + 7, Y + 7], outline=color, width=3); d.line([X, Y, X + 26 * math.cos(a), Y - 26 * math.sin(a)], fill=color, width=3)
            d.text((X + 9, Y + 6), name, fill=color)
        elif kind == 'path':
            d.line([px(x, y) for x, y in data], fill=color, width=2)
        elif kind == 'box':
            (a, b, c, e), name = data; d.rectangle([px(a, e), px(b, c)], outline=color, width=3); d.text((px(a, e)[0] + 4, px(a, e)[1] + 4), name, fill=color)
    if title: d.rectangle([0, 0, len(title) * 7 + 10, 16], fill=(255, 255, 255)); d.text((4, 2), title, fill=(0, 0, 0))
    im.save(path); return im
