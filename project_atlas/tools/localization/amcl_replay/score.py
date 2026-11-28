"""Score AMCL pose estimates by scan-to-map agreement (independent of AMCL's own covariance).
For each pose, take the scan with the nearest stamp, project beam endpoints (0.15..8 m) with the pose and the
base_link->laser static TF, and count endpoints within 1 cell of an occupied map cell.
Usage: score.py BAG MAP_YAML POSES.jsonl [...]"""
import bisect, json, math, os, sys
import yaml, rosbag2_py
from rclpy.serialization import deserialize_message
from sensor_msgs.msg import LaserScan
from tf2_msgs.msg import TFMessage

bag, map_yaml, files = sys.argv[1], sys.argv[2], sys.argv[3:]
meta = yaml.safe_load(open(map_yaml))
pgm = os.path.join(os.path.dirname(map_yaml), meta['image'])


def read_pgm(p):
    data = open(p, 'rb').read(); toks = []; i = 0
    while len(toks) < 4:
        while data[i:i + 1].isspace(): i += 1
        if data[i:i + 1] == b'#':
            while data[i:i + 1] != b'\n': i += 1
            continue
        j = i
        while not data[j:j + 1].isspace(): j += 1
        toks.append(data[i:j]); i = j
    i += 1
    w, h = int(toks[1]), int(toks[2])
    return w, h, data[i:i + w * h]


W, H, px = read_pgm(pgm)
res = float(meta['resolution']); ox, oy = meta['origin'][0], meta['origin'][1]
neg = int(meta.get('negate', 0)); occ_th = float(meta.get('occupied_thresh', 0.65))
occ = [((px[k] / 255.0) if neg else ((255 - px[k]) / 255.0)) > occ_th for k in range(W * H)]
dil = bytearray(W * H)
for k, o in enumerate(occ):
    if o:
        y, x = divmod(k, W)
        for dy in (-1, 0, 1):
            for dx in (-1, 0, 1):
                if 0 <= x + dx < W and 0 <= y + dy < H: dil[(y + dy) * W + x + dx] = 1

r = rosbag2_py.SequentialReader()
r.open(rosbag2_py.StorageOptions(uri=bag, storage_id='sqlite3'), rosbag2_py.ConverterOptions('cdr', 'cdr'))
r.set_filter(rosbag2_py.StorageFilter(topics=['/scan', '/tf_static']))
scans = []; lx = ly = lyaw = 0.0
while r.has_next():
    topic, data, ts = r.read_next()
    if topic == '/tf_static':
        for t in deserialize_message(data, TFMessage).transforms:
            if t.header.frame_id == 'base_link' and 'laser' in t.child_frame_id:
                q = t.transform.rotation
                lx, ly, lyaw = t.transform.translation.x, t.transform.translation.y, 2 * math.atan2(q.z, q.w)
    else:
        m = deserialize_message(data, LaserScan)
        scans.append((m.header.stamp.sec + m.header.stamp.nanosec * 1e-9, m))
st = [s[0] for s in scans]


def score(x, y, yaw, scan):
    hit = tot = 0
    c, s = math.cos(yaw), math.sin(yaw)
    sx, sy = x + c * lx - s * ly, y + s * lx + c * ly
    a = yaw + lyaw + scan.angle_min
    for rr in scan.ranges:
        if math.isfinite(rr) and 0.15 < rr < 8.0:
            gx = int((sx + rr * math.cos(a) - ox) / res); gy = int((sy + rr * math.sin(a) - oy) / res)
            tot += 1
            if 0 <= gx < W and 0 <= gy < H and dil[(H - 1 - gy) * W + gx]: hit += 1
        a += scan.angle_increment
    return hit / tot if tot else None


for fn in files:
    rows_all = [json.loads(l) for l in open(fn)]
    for kind in ('live', 'replay'):
        sc = []; sd = []
        for p in (q for q in rows_all if q['kind'] == kind):
            i = bisect.bisect_left(st, p['t'])
            cand = [j for j in (i - 1, i) if 0 <= j < len(st)]
            if not cand: continue
            j = min(cand, key=lambda j: abs(st[j] - p['t']))
            if abs(st[j] - p['t']) > 0.25: continue
            v = score(p['x'], p['y'], math.radians(p['yaw']), scans[j][1])
            if v is not None: sc.append(v); sd.append(p['sd_xy'])
        if not sc:
            print('%-24s %-6s no rows' % (os.path.basename(fn), kind)); continue
        ss = sorted(sc)
        print('%-24s %-6s n=%3d scan-fit mean=%.3f p10=%.3f | sd_xy mean=%.3f max=%.3f' % (
            os.path.basename(fn), kind, len(sc), sum(sc) / len(sc), ss[len(ss) // 10], sum(sd) / len(sd), max(sd)))
