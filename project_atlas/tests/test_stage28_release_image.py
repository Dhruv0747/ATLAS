import importlib.util
from pathlib import Path
import pytest

ROOT = Path(__file__).resolve().parents[1] / 'firmware/yahboom_rc_report'
spec = importlib.util.spec_from_file_location('release_image', ROOT / 'verify_release_image.py')
mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)


def record(kind, data=b'', address=0):
    raw = bytes([len(data)]) + address.to_bytes(2, 'big') + bytes([kind]) + data
    return ':' + (raw + bytes([-sum(raw) & 255])).hex()


def image(data, upper=0x800):
    return '\n'.join([record(4, upper.to_bytes(2, 'big')), record(0, data), record(1)])


DATA = bytes.fromhex('00c0002009000008') + b'\x00\xbf'


def test_valid():
    assert mod.verify(image(DATA), DATA)['settings_overlap'] is False


@pytest.mark.parametrize('text,data', [
    (image(DATA)[:-2] + '00', DATA),
    (image(DATA).replace(record(1), ''), DATA),
    (image(DATA, 0x804), DATA),
    (image(DATA), DATA + b'\x00'),
    (image(b'\xff' * 10), b'\xff' * 10),
    (image(DATA) + '\n' + record(0, DATA), DATA),
])
def test_reject_invalid(text, data):
    with pytest.raises(ValueError):
        mod.verify(text, data)


def test_preserved_float_display_and_pinned_dependencies():
    assert '-u,_printf_float' in (ROOT / 'Makefile.gcc').read_text()
    text = (ROOT / 'build_gcc.sh').read_text()
    assert 'SOURCE_DATE_EPOCH=1793077129' in text
    assert '628059b775ba7e0e5d7492291035c6f7c9870be5' in text
    assert 'c8e9a4a4f16b6d2cb2a2083cbe5161025280fb22' in text
    assert 'sha256sum -c -' in text
