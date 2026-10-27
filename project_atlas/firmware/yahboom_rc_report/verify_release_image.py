"""Offline-only independent HEX/BIN boundary and vector verification; never opens serial."""
import argparse
import hashlib
import json
from pathlib import Path


def verify(hex_data, binary):
    memory, base, eof = {}, 0, False
    for line in hex_data.splitlines():
        if not line.strip():
            continue
        if eof or not line.startswith(':'):
            raise ValueError('invalid record ordering')
        record = bytes.fromhex(line[1:])
        if len(record) < 5 or len(record) != record[0] + 5 or sum(record) & 255:
            raise ValueError('record length/checksum')
        n, address, kind = record[0], int.from_bytes(record[1:3], 'big'), record[3]
        payload = record[4:-1]
        if kind == 0:
            for offset, value in enumerate(payload):
                target = base + address + offset
                if not 0x08000000 <= target < 0x0803C000 or target in memory:
                    raise ValueError('outside application or duplicate address')
                memory[target] = value
        elif kind == 4 and n == 2 and address == 0:
            base = int.from_bytes(payload, 'big') << 16
        elif kind == 1 and n == 0 and address == 0:
            eof = True
        elif kind == 5 and n == 4 and address == 0:
            pass
        else:
            raise ValueError('unsupported HEX record')
    if not eof or not memory or min(memory) != 0x08000000:
        raise ValueError('missing EOF/application')
    image = bytes(memory.get(i, 0) for i in range(0x08000000, max(memory) + 1))
    if image != binary or len(binary) < 8:
        raise ValueError('HEX/BIN mismatch')
    sp, reset = (int.from_bytes(binary[i:i+4], 'little') for i in (0, 4))
    if not 0x20000000 < sp <= 0x2000C000 or sp % 8 or not reset & 1 or (reset & ~1) not in memory:
        raise ValueError('invalid startup vectors')
    return dict(bytes=len(binary), end=hex(max(memory)), stack=hex(sp), reset=hex(reset),
                sha256=hashlib.sha256(binary).hexdigest(), settings_overlap=False)


if __name__ == '__main__':
    p = argparse.ArgumentParser()
    p.add_argument('hex', type=Path)
    p.add_argument('bin', type=Path)
    a = p.parse_args()
    print(json.dumps(verify(a.hex.read_text(), a.bin.read_bytes()), indent=2))
