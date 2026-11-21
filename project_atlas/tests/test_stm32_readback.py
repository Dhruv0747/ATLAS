"""B1 pre-flight: the read-only STM32 bootloader backup tool against a simulated AN3155 bootloader."""
import hashlib
import json
import re
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'tools' / 'diagnostics' / 'stm32_readback'))
import atlas_stm32_readback as rb      # noqa: E402

TOOL = ROOT / 'tools' / 'diagnostics' / 'stm32_readback' / 'atlas_stm32_readback.py'
DESTRUCTIVE = {0x21: 'GO', 0x31: 'WRITE', 0x43: 'ERASE', 0x44: 'EXT_ERASE', 0x63: 'WRITE_PROTECT',
               0x73: 'WRITE_UNPROTECT', 0x82: 'READOUT_PROTECT', 0x92: 'READOUT_UNPROTECT'}


class FakeBootloader:
    """Byte-level AN3155 model: answers 0x7F, GET, GET_VERSION, GET_ID, READ_MEMORY; logs every command."""

    def __init__(self, flash_kb=256, rdp=False, pid=0x0414, fsize=None, flaky_at=None, silent=False):
        self.flash = bytearray(b'\xff' * flash_kb * 1024)
        self.flash[:8] = bytes.fromhex('6062002031010008')
        self.flash[120 * 2048:120 * 2048 + 8] = bytes.fromhex('0000' '55aa' '0500' '0100')
        self.flash[120 * 2048 + 0x70:120 * 2048 + 0x72] = (90).to_bytes(2, 'little')
        self.mem = {0x1FFFF800: bytes([0xA5 if not rdp else 0x00, 0x5A if not rdp else 0xFF]) + b'\xff' * 14,
                    0x1FFFF7E0: (fsize if fsize is not None else flash_kb).to_bytes(2, 'little'),
                    0x1FFFF7E8: bytes(range(12))}
        self.rdp, self.pid, self.flaky_at, self.silent = rdp, pid, flaky_at, silent
        self.inbuf, self.out = bytearray(), bytearray()
        self.commands, self.reads, self.state = [], 0, 'idle'

    def write(self, b):
        self.inbuf += b
        self._run()

    def read(self, n=1):
        b, self.out = bytes(self.out[:n]), self.out[n:]
        return b

    def _run(self):
        ACK, NACK = b'\x79', b'\x1f'
        while True:
            if self.silent:
                self.inbuf.clear()
                return
            if self.state == 'idle':
                if not self.inbuf:
                    return
                if self.inbuf[0] == 0x7F and len(self.commands) == 0 and not self.out:
                    del self.inbuf[0]
                    self.out += ACK
                    continue
                if len(self.inbuf) < 2:
                    return
                c, x = self.inbuf[0], self.inbuf[1]
                del self.inbuf[:2]
                self.commands.append(c)
                if c ^ x != 0xFF:
                    self.out += NACK
                elif c == 0x00:
                    cmds = bytes([0x00, 0x01, 0x02, 0x11, 0x21, 0x31, 0x43, 0x63, 0x73, 0x82, 0x92])
                    self.out += ACK + bytes([len(cmds)]) + b'\x22' + cmds + ACK
                elif c == 0x01:
                    self.out += ACK + b'\x22\x00\x00' + ACK
                elif c == 0x02:
                    self.out += ACK + b'\x01' + self.pid.to_bytes(2, 'big') + ACK
                elif c == 0x11:
                    if self.rdp:
                        self.out += NACK
                    else:
                        self.out += ACK
                        self.state = 'addr'
                else:
                    self.out += NACK      # the tool must never get here
            elif self.state == 'addr':
                if len(self.inbuf) < 5:
                    return
                a = bytes(self.inbuf[:5])
                del self.inbuf[:5]
                if a[0] ^ a[1] ^ a[2] ^ a[3] != a[4]:
                    self.out += NACK
                    self.state = 'idle'
                    continue
                self.addr = int.from_bytes(a[:4], 'big')
                self.out += ACK
                self.state = 'len'
            elif self.state == 'len':
                if len(self.inbuf) < 2:
                    return
                n, x = self.inbuf[0], self.inbuf[1]
                del self.inbuf[:2]
                self.state = 'idle'
                if n ^ x != 0xFF:
                    self.out += NACK
                    continue
                self.reads += 1
                if self.flaky_at is not None and self.reads == self.flaky_at:
                    self.out += NACK
                    continue
                self.out += ACK + self._mem(self.addr, n + 1)

    def _mem(self, a, n):
        if 0x08000000 <= a < 0x08000000 + len(self.flash):
            o = a - 0x08000000
            return bytes(self.flash[o:o + n])
        for base, data in self.mem.items():
            if base <= a < base + len(data):
                return data[a - base:a - base + n]
        return b'\x00' * n


def _vendor_like_hex(tmp_path, image):
    p = tmp_path / 'ref.hex'
    rb.write_ihex(p, image[:0x100])
    return str(p)


def test_full_backup_reads_twice_and_decodes_settings(tmp_path):
    bl = FakeBootloader()
    code = rb.backup(rb.BootloaderClient(bl, timeout_s=0.2), tmp_path / 'out',
                     [_vendor_like_hex(tmp_path, bytes(bl.flash))], log=lambda *_: None)
    assert code == 0
    meta = json.loads((tmp_path / 'out' / 'meta.json').read_text())
    img = (tmp_path / 'out' / 'flash_full.bin').read_bytes()
    assert img == bytes(bl.flash) and meta['flash_sha256'] == hashlib.sha256(img).hexdigest()
    assert meta['product_id'] == '0x0414' and meta['flash_size_kb_register'] == 256
    assert meta['read_protection'].startswith('inactive') and meta['verify'] == 'two passes identical'
    s = meta['settings']
    assert s['reset_marker_ok'] and s['car_type'] == 5 and s['auto_report'] == 1 and s['akm_default_angle'] == 90
    assert meta['vendor_compare'][0]['identical'] is True
    assert set(bl.commands) <= rb.ALLOWED_COMMANDS
    assert bl.reads == 3 + 2 * 1024           # option bytes, F_SIZE, UID, then two full passes
    sums = (tmp_path / 'out' / 'SHA256SUMS').read_text()
    assert 'flash_full.bin' in sums and 'settings_sector120.bin' in sums
    hx = rb.parse_ihex(str(tmp_path / 'out' / 'flash_full.hex'))
    assert bytes(hx[0x08000000 + i] for i in range(16)) == img[:16] and len(hx) == len(img)


def test_512k_part_uses_flash_size_register(tmp_path):
    bl = FakeBootloader(flash_kb=512)          # e.g. the APM32E103RET6 footprint option
    assert rb.backup(rb.BootloaderClient(bl, 0.2), tmp_path / 'o', [], log=lambda *_: None) == 0
    assert len((tmp_path / 'o' / 'flash_full.bin').read_bytes()) == 512 * 1024


def test_read_protection_is_reported_and_never_unlocked(tmp_path):
    bl = FakeBootloader(rdp=True)
    code = rb.backup(rb.BootloaderClient(bl, 0.2), tmp_path / 'o', [], log=lambda *_: None)
    meta = json.loads((tmp_path / 'o' / 'meta.json').read_text())
    assert code == 3 and meta['read_protection'].startswith('ACTIVE')
    assert 0x92 not in bl.commands and set(bl.commands) <= rb.ALLOWED_COMMANDS
    assert not (tmp_path / 'o' / 'flash_full.bin').exists()


def test_first_nack_stops_without_retry(tmp_path):
    bl = FakeBootloader(flaky_at=50)
    code = rb.backup(rb.BootloaderClient(bl, 0.2), tmp_path / 'o', [], log=lambda *_: None)
    meta = json.loads((tmp_path / 'o' / 'meta.json').read_text())
    assert code == 3 or code == 4
    assert bl.reads == 50 and 'no automatic retry' in meta.get('error', 'no automatic retry')


def test_silent_port_times_out(tmp_path):
    bl = FakeBootloader(silent=True)
    code = rb.backup(rb.BootloaderClient(bl, 0.1), tmp_path / 'o', [], log=lambda *_: None)
    assert code == 4 and bl.commands == []


def test_unknown_chip_id_is_flagged(tmp_path):
    bl = FakeBootloader(pid=0x0430)
    rb.backup(rb.BootloaderClient(bl, 0.2), tmp_path / 'o', [], log=lambda *_: None)
    meta = json.loads((tmp_path / 'o' / 'meta.json').read_text())
    assert meta['product_id_meaning'].startswith('UNKNOWN')


@pytest.mark.parametrize('cmd', sorted(DESTRUCTIVE))
def test_destructive_commands_refused_before_sending(cmd):
    bl = FakeBootloader()
    c = rb.BootloaderClient(bl, 0.2)
    with pytest.raises(rb.Refused):
        c._command(cmd)
    assert bl.commands == []


def test_source_has_no_destructive_command_constants():
    src = TOOL.read_text()
    code = re.sub(r'""".*?"""', '', src, flags=re.S)      # docstrings name the forbidden commands
    code = re.sub(r'#.*', '', code)
    for value, name in DESTRUCTIVE.items():
        assert not re.search(r'\b0x%02X\b' % value, code, re.I), name
    assert re.search(r'ALLOWED_COMMANDS = frozenset\(\{CMD_GET, CMD_GET_VERSION, CMD_GET_ID, CMD_READ\}\)', src)
    assert 'serial.Serial(' in src and 'exclusive=True' in src and 'link.dtr = False' in src


def test_settings_decoder_on_erased_sector():
    s = rb.decode_settings(b'\xff' * 2048)
    assert s['erased'] and not s['reset_marker_ok'] and s['motor_pid'] is None


def test_cli_refuses_without_confirmation_or_on_wrong_port(tmp_path, capsys):
    assert rb.main(['--port', '/dev/ttyUSB0', '--out', str(tmp_path)]) == 2
    assert 'REFUSED' in capsys.readouterr().err
    assert rb.main(['--port', '/dev/does-not-exist', '--out', str(tmp_path), '--i-confirm-bootloader-entered']) == 2
    assert 'expected' in capsys.readouterr().err
