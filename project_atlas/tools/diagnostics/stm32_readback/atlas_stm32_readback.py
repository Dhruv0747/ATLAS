#!/usr/bin/env python3
"""ATLAS B1: READ-ONLY backup of the Yahboom board's STM32 through its built-in ROM bootloader.

PROPOSAL. Run only under the separately approved B1 gate. This tool cannot write, erase, unprotect,
change option bytes or jump to code. It sends only these bootloader commands (AN3155):

    0x7F  autobaud sync          0x00 GET             0x01 GET_VERSION
    0x02  GET_ID                 0x11 READ_MEMORY

Anything else raises before a byte is sent. In particular it never sends 0x92 READOUT_UNPROTECT (that
mass-erases the chip), 0x43/0x44 erase, 0x31 write, 0x63/0x73 write-protect changes, 0x82 readout-protect
or 0x21 GO. There are no automatic retries: the first NACK or timeout stops the run with a report.

Board facts (YB-ERF01 V3.0 schematic, Yahboom 2025-05-09):
  * USART1 (PA9/PA10) is wired to the CH340N on the micro-USB port; the CH340N RTS pin is NOT connected
    and the CH340N has no DTR pin, so software cannot reset the MCU or enter the bootloader.
    Entry is physical only: hold BOOT0 (S4), press and release RESET (S2), release BOOT0.
  * BOOT1/PB2 is pulled down (R31 100k): BOOT0=1 selects system memory (the ROM bootloader).
  * The MCU footprint is marked "APM32E103RET6/STM32F103RCT6": the real flash size is read from the chip
    (F_SIZE register) instead of being assumed.
Read protection check: with RDP level 1 set, the bootloader NACKs READ_MEMORY. That is reported and the
run stops; nothing is done to remove the protection.

Exit codes: 0 full backup written, 2 refused before talking to the chip, 3 read protection active,
            4 protocol error/timeout (stopped, no retry), 5 the two read passes differ.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import struct
import sys
import time
from pathlib import Path
from typing import Dict, List, Optional

ACK, NACK = 0x79, 0x1F
SYNC = 0x7F
CMD_GET, CMD_GET_VERSION, CMD_GET_ID, CMD_READ = 0x00, 0x01, 0x02, 0x11
ALLOWED_COMMANDS = frozenset({CMD_GET, CMD_GET_VERSION, CMD_GET_ID, CMD_READ})
FLASH_BASE = 0x08000000
OPTION_BYTES = 0x1FFFF800
F_SIZE = 0x1FFFF7E0
UID = 0x1FFFF7E8
CHUNK = 256
SETTINGS_SECTOR = 120          # app_flash.h FLASH_DATA_SECTOR, 2 KB pages on high-density parts
PAGE = 2048
KNOWN_PIDS = {0x0414: 'STM32F10x high-density (e.g. STM32F103RC/RE) or compatible'}


class Refused(Exception):
    pass


class ProtocolError(Exception):
    pass


class ReadProtected(Exception):
    pass


class BootloaderClient:
    """Minimal AN3155 client. `link` needs read(n) -> bytes (may return fewer on timeout) and write(b)."""

    def __init__(self, link, timeout_s: float = 1.0):
        self.link = link
        self.timeout_s = timeout_s
        self.sent_commands: List[int] = []

    # -- low level
    def _read_exact(self, n: int) -> bytes:
        out = b''
        deadline = time.monotonic() + self.timeout_s
        while len(out) < n:
            chunk = self.link.read(n - len(out))
            if chunk:
                out += chunk
            elif time.monotonic() > deadline:
                raise ProtocolError('timeout waiting for %d byte(s), got %d' % (n, len(out)))
        return out

    def _ack(self, what: str) -> None:
        b = self._read_exact(1)[0]
        if b == NACK:
            raise ProtocolError('NACK after ' + what)
        if b != ACK:
            raise ProtocolError('unexpected byte 0x%02X after %s' % (b, what))

    def _command(self, cmd: int) -> None:
        if cmd not in ALLOWED_COMMANDS:
            raise Refused('command 0x%02X is not allowed by this read-only tool' % cmd)
        self.sent_commands.append(cmd)
        self.link.write(bytes([cmd, cmd ^ 0xFF]))
        self._ack('command 0x%02X' % cmd)

    # -- protocol
    def sync(self) -> str:
        self.link.write(bytes([SYNC]))
        b = self._read_exact(1)[0]
        if b == ACK:
            return 'ack'
        raise ProtocolError('no bootloader answer to 0x7F (got 0x%02X)' % b)

    def get(self) -> Dict:
        self._command(CMD_GET)
        n = self._read_exact(1)[0]
        data = self._read_exact(n + 1)
        self._ack('GET data')
        return {'bootloader_version': '%d.%d' % (data[0] >> 4, data[0] & 15),
                'commands': ['0x%02X' % c for c in data[1:]]}

    def get_version(self) -> Dict:
        self._command(CMD_GET_VERSION)
        data = self._read_exact(3)
        self._ack('GET_VERSION data')
        return {'version_byte': '0x%02X' % data[0], 'option_byte_1': '0x%02X' % data[1],
                'option_byte_2': '0x%02X' % data[2]}

    def get_id(self) -> int:
        self._command(CMD_GET_ID)
        n = self._read_exact(1)[0]
        data = self._read_exact(n + 1)
        self._ack('GET_ID data')
        return int.from_bytes(data, 'big')

    def read(self, address: int, length: int) -> bytes:
        if not 1 <= length <= 256:
            raise ValueError('length 1..256')
        try:
            self._command(CMD_READ)
        except ProtocolError as exc:
            if 'NACK' in str(exc):
                raise ReadProtected('READ_MEMORY command refused (read-out protection active)') from None
            raise
        addr = struct.pack('>I', address)
        self.link.write(addr + bytes([addr[0] ^ addr[1] ^ addr[2] ^ addr[3]]))
        try:
            self._ack('address 0x%08X' % address)
        except ProtocolError as exc:
            if 'NACK' in str(exc):
                raise ReadProtected('address 0x%08X refused (read-out protection or invalid address)'
                                    % address) from None
            raise
        n = length - 1
        self.link.write(bytes([n, n ^ 0xFF]))
        self._ack('length %d' % length)
        return self._read_exact(length)


# ------------------------------------------------------------------------------------------- decoding
def decode_settings(sector: bytes) -> Dict:
    """Yahboom app_flash.h layout (uint16 little-endian half-words, PID stored x1000)."""
    def u16(off):
        return int.from_bytes(sector[off:off + 2], 'little')

    def pid(off):
        v = [u16(off + 2 * i) for i in range(3)]
        return None if v == [0xFFFF] * 3 else [x / 1000.0 for x in v]
    erased = all(b == 0xFF for b in sector[:0x80])
    return {
        'erased': erased,
        'reset_marker_ok': u16(0x02) == 0xAA55,
        'test_mode': u16(0x00),
        'car_type': u16(0x04),
        'auto_report': u16(0x06),
        'imu_state': u16(0x0A),
        'rgb_effect': u16(0x10),
        'yaw_pid': pid(0x20),
        'motor_pid': pid(0x30),
        'arm_offsets': [u16(0x50 + 2 * i) for i in range(7)],
        'akm_default_angle': u16(0x70),
        'raw_0x00_0x80': sector[:0x80].hex(),
    }


def parse_ihex(path: str) -> Dict[int, int]:
    data, base = {}, 0
    for line in open(path):
        line = line.strip()
        if not line.startswith(':'):
            continue
        b = bytes.fromhex(line[1:])
        if b[3] == 4:
            base = ((b[4] << 8) | b[5]) << 16
        elif b[3] == 0:
            addr = base + ((b[1] << 8) | b[2])
            for i in range(b[0]):
                data[addr + i] = b[4 + i]
    return data


def compare_with_hex(image: bytes, hex_path: str) -> Dict:
    ref = parse_ihex(hex_path)
    lo, hi = min(ref), max(ref)
    diffs = [a for a in range(lo, hi + 1) if a - FLASH_BASE < len(image) and
             image[a - FLASH_BASE] != ref.get(a, 0xFF)]
    return {'reference': os.path.basename(hex_path), 'reference_sha256': hashlib.sha256(open(hex_path, 'rb').read()).hexdigest(),
            'range': '0x%08X-0x%08X' % (lo, hi), 'differing_bytes': len(diffs),
            'first_differences': ['0x%08X' % a for a in diffs[:8]], 'identical': not diffs}


def write_ihex(path: Path, image: bytes, base: int = FLASH_BASE) -> None:
    lines = []
    for off in range(0, len(image), 16):
        addr = base + off
        if off % 0x10000 == 0:
            rec = bytes([2, 0, 0, 4]) + struct.pack('>H', addr >> 16)
            lines.append(':' + (rec + bytes([(-sum(rec)) & 0xFF])).hex().upper())
        chunk = image[off:off + 16]
        rec = bytes([len(chunk)]) + struct.pack('>H', addr & 0xFFFF) + b'\x00' + chunk
        lines.append(':' + (rec + bytes([(-sum(rec)) & 0xFF])).hex().upper())
    lines.append(':00000001FF')
    path.write_text('\n'.join(lines) + '\n')


# ------------------------------------------------------------------------------------------- run
def backup(client: BootloaderClient, out: Path, vendor_hexes: List[str], log=print,
           guard=lambda: None) -> int:
    out.mkdir(parents=True, exist_ok=False)
    meta: Dict = {'tool': 'atlas_stm32_readback', 'started': time.strftime('%Y-%m-%dT%H:%M:%S%z')}

    def finish(code: int) -> int:
        meta['exit_code'] = code
        meta['commands_sent'] = ['0x%02X' % c for c in client.sent_commands]
        (out / 'meta.json').write_text(json.dumps(meta, indent=2))
        log(json.dumps({k: meta[k] for k in meta if k not in ('settings',)}, indent=2)[:4000])
        return code

    try:
        guard()
        meta['sync'] = client.sync()
        meta['get'] = client.get()
        meta['get_version'] = client.get_version()
        pid = client.get_id()
        meta['product_id'] = '0x%04X' % pid
        meta['product_id_meaning'] = KNOWN_PIDS.get(pid, 'UNKNOWN: stop and identify the chip before B2')
        if pid != 0x0414:
            raise Refused('unsupported MCU ID; expected 0x0414 plus owner-confirmed STM32F103RCT6 marking')
        try:
            opt = client.read(OPTION_BYTES, 16)
        except ReadProtected as exc:
            meta['read_protection'] = 'DENIED/UNKNOWN (%s). Nothing was unlocked or erased.' % exc
            return finish(3)
        (out / 'option_bytes.bin').write_bytes(opt)
        meta['option_bytes'] = opt.hex()
        if len(opt) != 16:
            raise Refused('missing option-byte evidence')
        meta['rdp_byte'] = '0x%02X' % opt[0]
        meta['read_protection'] = 'inactive (RDP byte 0xA5)' if opt[0] == 0xA5 else \
            'UNEXPECTED RDP byte 0x%02X although reads work' % opt[0]
        if len(opt) != 16 or opt[:2] != b'\xa5\x5a':
            raise Refused('protected or ambiguous RDP/complement; no flash read permitted')
        raw_size = client.read(F_SIZE, 2)
        if len(raw_size) != 2:
            raise Refused('missing flash-size evidence')
        fsize = int.from_bytes(raw_size, 'little')
        meta['flash_size_kb_register'] = fsize
        if fsize != 256:
            raise Refused('unexpected flash capacity: require exactly 256 KB for owner-confirmed RC')
        uid = client.read(UID, 12)
        if len(uid) != 12:
            raise Refused('missing UID evidence')
        meta['uid'] = uid.hex()
        size = fsize * 1024
        passes = []
        for p in range(2):
            img = bytearray()
            t0 = time.monotonic()
            for off in range(0, size, CHUNK):
                guard()
                data = client.read(FLASH_BASE + off, min(CHUNK, size - off))
                if len(data) != min(CHUNK, size - off):
                    raise Refused('incomplete flash chunk')
                img += data
                if p == 0 and off == 0:
                    log('BACKUP STARTED — DO NOT PRESS BUTTONS.')
            guard()
            passes.append(bytes(img))
            (out / ('flash_pass%d.bin' % (p + 1))).write_bytes(passes[-1])
            meta['pass%d_sha256' % (p + 1)] = hashlib.sha256(passes[-1]).hexdigest()
            meta['pass%d_seconds' % (p + 1)] = round(time.monotonic() - t0, 1)
        if passes[0] != passes[1]:
            meta['verify'] = 'MISMATCH between the two read passes'
            (out / 'flash_pass1.bin').write_bytes(passes[0])
            (out / 'flash_pass2.bin').write_bytes(passes[1])
            return finish(5)
        image = passes[0]
        (out / 'flash_full.bin').write_bytes(image)
        write_ihex(out / 'flash_full.hex', image)
        meta['flash_sha256'] = hashlib.sha256(image).hexdigest()
        meta['verify'] = 'two passes identical'
        sector = image[SETTINGS_SECTOR * PAGE:(SETTINGS_SECTOR + 1) * PAGE]
        (out / 'settings_sector120.bin').write_bytes(sector)
        meta['settings'] = decode_settings(sector)
        used = len(image.rstrip(b'\xff'))
        meta['last_programmed_byte'] = '0x%08X' % (FLASH_BASE + used - 1)
        meta['vendor_compare'] = [compare_with_hex(image, h) for h in vendor_hexes]
        with open(out / 'SHA256SUMS', 'w') as f:
            for name in ('flash_pass1.bin', 'flash_pass2.bin', 'flash_full.bin', 'flash_full.hex', 'option_bytes.bin', 'settings_sector120.bin'):
                f.write('%s  %s\n' % (hashlib.sha256((out / name).read_bytes()).hexdigest(), name))
        return finish(0)
    except (Refused, KeyboardInterrupt, OSError) as exc:
        meta['error'] = '%s: %s; stopped with no automatic retry' % (type(exc).__name__, exc)
        return finish(2 if isinstance(exc, Refused) else 4)
    except ProtocolError as exc:
        meta['error'] = str(exc) + ' (stopped; no automatic retry)'
        return finish(4)


def _usb_location(dev: str) -> Optional[str]:
    try:
        from serial.tools import list_ports
        for p in list_ports.comports():
            if os.path.realpath(p.device) == os.path.realpath(dev):
                return '%s|%04x:%04x' % (p.location, p.vid or 0, p.pid or 0)
    except Exception:
        return None
    return None


def main(argv=None) -> int:            # pragma: no cover - needs the board in bootloader mode
    ap = argparse.ArgumentParser(description=__doc__.split('\n')[0])
    ap.add_argument('--maintenance-session', required=False)
    ap.add_argument('--port', required=True)
    ap.add_argument('--expect-location', default='1-2.2.3|1a86:7523',
                    help='pyserial location|vid:pid that must match (Yahboom board, measured 2026-10-27)')
    ap.add_argument('--out', required=True)
    ap.add_argument('--vendor-hex', action='append', default=[])
    ap.add_argument('--i-confirm-bootloader-entered', action='store_true',
                    help='operator confirms: base service stopped, board main switch ON, battery connected, all actuators physically disconnected, BOOT0+RESET done')
    a = ap.parse_args(argv)
    if not a.i_confirm_bootloader_entered:
        print('REFUSED: pass --i-confirm-bootloader-entered after the B1 physical steps', file=sys.stderr)
        return 2
    loc = _usb_location(a.port)
    if loc != a.expect_location:
        print('REFUSED: %s is at %r, expected %r (not the Yahboom board?)' % (a.port, loc, a.expect_location),
              file=sys.stderr)
        return 2
    scripts = os.environ.get('ATLAS_SCRIPTS_DIR', '/home/jetson/project_atlas/scripts')
    if not Path(scripts, 'atlas_usb_identity.py').exists():          # running from the repo checkout
        scripts = str(Path(__file__).resolve().parents[3] / 'scripts')
    sys.path.insert(0, scripts)
    from atlas_usb_identity import in_use
    if in_use(os.path.realpath(a.port)):
        print('REFUSED: the port is held by another process (stop rover-base-telemetry first, B1 step)',
              file=sys.stderr)
        return 2
    from atlas_b1_interlock import Interlock
    interlock = Interlock()
    def read_guard():
        try:
            interlock.check_read(a.maintenance_session)
        except Exception as exc:
            raise Refused('maintenance read gate: ' + str(exc)) from exc
    try:
        read_guard()
    except Refused as exc:
        print('REFUSED:', exc, file=sys.stderr)
        return 2
    import serial
    link = serial.Serial(port=None, baudrate=115200, parity=serial.PARITY_EVEN, stopbits=1, bytesize=8,
                         timeout=0.2, write_timeout=1.0, exclusive=True)
    link.dtr = False
    link.rts = False
    link.port = a.port
    link.open()
    try:
        link.reset_input_buffer()
        time.sleep(0.3)
        stray = link.read(64)
        if b'\xff\xfb' in stray:
            print('REFUSED: the board is sending its normal firmware packets; it is NOT in the bootloader. '
                  'Attempt aborted; do not retry without review.', file=sys.stderr)
            return 2
        return backup(BootloaderClient(link), Path(a.out), a.vendor_hex, guard=read_guard)
    finally:
        link.close()
        print('Done. Leave BOOT0 released and press RESET (with the board main switch ON) to restart the '
              'firmware; the bootloader GO command is deliberately not used.')


if __name__ == '__main__':
    raise SystemExit(main())
