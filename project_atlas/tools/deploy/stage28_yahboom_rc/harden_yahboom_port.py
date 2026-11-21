#!/usr/bin/env python3
"""Stage 28 (proposal): remove the ambiguous CH340 fallbacks from yahboom_base.resolve_yahboom_port().

Today's fallback list ends with '/dev/serial/by-id/usb-1a86_USB_Serial-if00-port0' and a glob of the same
name. All three ATLAS CH340s (Yahboom, GPS, IMU) share that by-id name, so the link points at whichever
enumerated last (measured 2026-10-27: it points at ttyUSB1 = GPS). The live service is unaffected
because it runs with ATLAS_YAHBOOM_AUTO_USB=1 (protocol-verified discovery), but if that variable were
ever dropped the driver would open the GPS as the motor board. After this edit the non-auto path accepts
only an explicit ATLAS_YAHBOOM_PORT or the topology-pinned /dev/atlas-yahboom, and fails closed otherwise.
Usage: harden_yahboom_port.py <yahboom_base.py>
"""
import sys

OLD = """    candidates = [
        configured,
        '/dev/yahboom',
        '/dev/atlas-yahboom',
        YAHBOOM_USB_ID,
    ]
    by_id = Path('/dev/serial/by-id')
    if by_id.is_dir():
        candidates.extend(str(path) for path in sorted(
            by_id.glob('usb-1a86_USB_Serial*-if00-port0')
        ))
"""
NEW = """    # ATLAS Stage 28: no ambiguous CH340 names. '/dev/yahboom' and the shared by-id link
    # usb-1a86_USB_Serial-if00-port0 can resolve to the GPS or IMU adapter (no serial numbers).
    # Only the topology-pinned udev hint is accepted; protocol-verified discovery
    # (ATLAS_YAHBOOM_AUTO_USB=1) remains the production path.
    candidates = [
        '/dev/atlas-yahboom',
    ]
"""


def patch(text: str) -> str:
    if 'ATLAS Stage 28: no ambiguous CH340 names' in text:
        raise SystemExit('already patched')
    if text.count(OLD) != 1:
        raise SystemExit('anchor missing or not unique')
    return text.replace(OLD, NEW)


if __name__ == '__main__':
    path = sys.argv[1]
    out = patch(open(path, encoding='utf-8').read())
    compile(out, path, 'exec')
    open(path, 'w', encoding='utf-8').write(out)
    print('patched', path)
