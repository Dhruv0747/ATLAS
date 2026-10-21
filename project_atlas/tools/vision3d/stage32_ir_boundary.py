"""Stage32 takeover: classify ONE instrumented IR session into the earliest failed delivery boundary (offline analysis).

Inputs (both produced without touching the camera after the session):
  driver log  -- ATLAS_IR_START / ATLAS_IR_PUBLISHER / ATLAS_IR_COUNTERS lines from the instrumented driver
  session     -- s32_session.py JSON (page-side status polls: receiver callbacks, raw fetch, canvas)
usage: python3 stage32_ir_boundary.py DRIVER_LOG SESSION_JSON
"""
import json
import re
import sys

BOUNDARIES = [
    (1, 'OpenNI stream readiness / readFrame'),
    (2, 'actual frame metadata'),
    (3, 'vendor frame callback'),
    (4, 'conversion to ROS Image'),
    (5, 'ROS publish attempt/return'),
    (6, 'domain-77 publisher/subscriber matching'),
    (7, 'receiver callbacks'),
    (8, 'web API delivery'),
    (9, 'browser canvas rendering'),
]


def parse_driver(text):
    out = {'start': None, 'publisher': None, 'final': None, 'periodic': []}
    for line in text.splitlines():
        if 'ATLAS_IR_START' in line:
            out['start'] = dict(re.findall(r'(\w+)=(\S+)', line.split('ATLAS_IR_START', 1)[1]))
        elif 'ATLAS_IR_PUBLISHER' in line:
            out['publisher'] = dict(re.findall(r'(\w+)=(\S+)', line.split('ATLAS_IR_PUBLISHER', 1)[1]))
        elif 'ATLAS_IR_COUNTERS' in line:
            kv = {k: int(v) if re.fullmatch(r'-?\d+', v) else v for k, v in re.findall(r'(\w+)=(\S+)', line.split('ATLAS_IR_COUNTERS', 1)[1])}
            (out.__setitem__('final', kv) if kv.get('final') == 1 else out['periodic'].append(kv))
    return out


def classify(driver, session):
    c = driver['final'] or (driver['periodic'][-1] if driver['periodic'] else None)
    ev = {'counters': c, 'start': driver['start'], 'publisher': driver['publisher']}
    if c is None:
        return {'earliest_failed': 0, 'name': 'INSTRUMENTATION ABSENT (no ATLAS_IR_COUNTERS line)', 'evidence': ev}
    if c.get('started', 0) < 1 or c.get('start_rc', -1) != 0:
        return {'earliest_failed': 1, 'name': 'stream did not start (start_rc=%s)' % c.get('start_rc'), 'evidence': ev}
    if c.get('ready', 0) == 0:
        return {'earliest_failed': 1, 'name': BOUNDARIES[0][1] + ': OpenNI never signalled an IR frame ready '
                '(wait_ok=%s wait_failed=%s last wait_rc=%s)' % (c.get('wait_ok'), c.get('wait_failed'), c.get('wait_rc')), 'evidence': ev}
    if c.get('read_ok', 0) == 0:
        return {'earliest_failed': 1, 'name': 'readFrame failed every time (read_rc=%s)' % c.get('read_rc'), 'evidence': ev}
    if c.get('callback', 0) == 0:
        return {'earliest_failed': 3, 'name': BOUNDARIES[2][1], 'evidence': ev}
    if not (c.get('width', 0) > 0 and c.get('height', 0) > 0 and c.get('bytes', 0) > 0):
        return {'earliest_failed': 2, 'name': 'frame metadata empty (w=%s h=%s bytes=%s)' % (c.get('width'), c.get('height'), c.get('bytes')), 'evidence': ev}
    if c.get('converted', 0) == 0:
        return {'earliest_failed': 4, 'name': BOUNDARIES[3][1], 'evidence': ev}
    if c.get('publish_returned', 0) == 0 or c.get('exceptions', 0):
        return {'earliest_failed': 5, 'name': BOUNDARIES[4][1] + ' (attempts=%s returned=%s exceptions=%s)' % (
            c.get('publish_attempt'), c.get('publish_returned'), c.get('exceptions')), 'evidence': ev}
    polls = [r for r in session.get('timeline', []) if 'streams' in r]
    rx = max([r['streams']['ir'].get('rx') or 0 for r in polls] or [0])
    rejected = max([r['streams']['ir'].get('rejected') or 0 for r in polls] or [0])
    peak_subs = max([p.get('subscribers', 0) for p in driver['periodic']] + [c.get('subscribers', 0)])
    ev.update(receiver_callbacks=rx, receiver_rejected=rejected, max_driver_subscribers=peak_subs)
    if peak_subs == 0:
        return {'earliest_failed': 6, 'name': BOUNDARIES[5][1] + ': driver published but never saw a subscriber', 'evidence': ev}
    if rx == 0:
        return {'earliest_failed': 7, 'name': BOUNDARIES[6][1] + ': subscriber matched but no receiver callback', 'evidence': ev}
    if not any(r['streams']['ir'].get('state') == 'ACTIVE' for r in polls):
        return {'earliest_failed': 7, 'name': 'receiver got %d IR messages but never held a fresh accepted frame (rejected=%d)' % (rx, rejected), 'evidence': ev}
    if not session.get('ir_canvas'):
        return {'earliest_failed': 8, 'name': BOUNDARIES[7][1] + ': page never obtained a raw IR frame', 'evidence': ev}
    cv = session['ir_canvas']
    if not (cv.get('w', 0) > 0 and cv.get('max', 0) > cv.get('min', 0)):
        return {'earliest_failed': 9, 'name': BOUNDARIES[8][1], 'evidence': ev}
    return {'earliest_failed': None, 'name': 'ALL BOUNDARIES PASSED: real IR frames rendered on the Dashboard', 'evidence': ev}


if __name__ == '__main__':
    d = parse_driver(open(sys.argv[1], errors='replace').read())
    s = json.load(open(sys.argv[2])) if len(sys.argv) > 2 else {}
    print(json.dumps(classify(d, s), indent=2))
