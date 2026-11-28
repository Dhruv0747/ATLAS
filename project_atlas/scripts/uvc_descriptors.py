"""Passive UVC capability parser (25 Oct 2026): reads the USB descriptors Linux caches in sysfs at enumeration.
Never opens /dev/video*, never touches the camera. Returns formats, frame sizes and frame rates the device advertises."""
from pathlib import Path

SUBTYPES = {0x04: 'YUYV', 0x06: 'MJPEG', 0x10: 'FRAME_BASED'}
FRAME_FOR = {0x05: 0x04, 0x07: 0x06, 0x11: 0x10}


def parse(raw):
    formats, cur, i = [], None, 0
    while i + 2 <= len(raw):
        ln, dtype = raw[i], raw[i + 1]
        if ln < 2 or i + ln > len(raw): break
        d = raw[i:i + ln]
        if dtype == 0x24 and ln >= 3:           # class-specific interface descriptor
            sub = d[2]
            if sub in SUBTYPES:
                name = SUBTYPES[sub]
                if sub == 0x04 and ln >= 21:     # uncompressed: GUID at 5..20, first 4 bytes = fourcc
                    name = bytes(d[5:9]).decode('ascii', 'replace').strip('\0') or 'YUYV'
                cur = {'format': name, 'sizes': []}; formats.append(cur)
            elif sub in FRAME_FOR and cur is not None and ln >= 26:
                w = d[5] | d[6] << 8; h = d[7] | d[8] << 8; n = d[25]
                fps = []
                if n:                            # discrete intervals, 100 ns units
                    for k in range(n):
                        o = 26 + 4 * k
                        if o + 4 <= ln:
                            iv = int.from_bytes(d[o:o + 4], 'little')
                            if iv: fps.append(round(1e7 / iv, 2))
                else:                            # continuous: min, max, step
                    lo = int.from_bytes(d[26:30], 'little'); hi = int.from_bytes(d[30:34], 'little')
                    fps = [round(1e7 / lo, 2), round(1e7 / hi, 2)] if lo and hi else []
                cur['sizes'].append({'w': w, 'h': h, 'fps': sorted(set(fps), reverse=True)})
        i += ln
    return formats


def read(sysfs_device):
    return parse((Path(sysfs_device) / 'descriptors').read_bytes())


if __name__ == '__main__':
    import json, sys
    print(json.dumps(read(sys.argv[1])))
