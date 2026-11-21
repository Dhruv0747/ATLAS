"""Camera-free checks for the exact C++ counters and pinned insertion anchors."""
import shutil,subprocess
from pathlib import Path
import pytest
TOOLS=Path(__file__).resolve().parents[1]/'tools/vision3d'

def test_native_counter_simulation(tmp_path):
    if not shutil.which('g++'):pytest.skip('native g++ unavailable')
    exe=tmp_path/'counters'
    subprocess.run(['g++','-std=c++17','-O2','-Wall','-Wextra',str(TOOLS/'test_ir_counters.cpp'),'-o',str(exe)],check=True)
    assert 'PASS counter simulation' in subprocess.check_output([str(exe)],text=True)

def test_instrumentation_preserves_settings_and_separates_boundaries():
    s=(TOOLS/'instrument_ir_driver.py').read_text()
    for token in ('Counters::callback','Counters::read_ok','Counters::read_failed',
                  'Counters::converted','Counters::publish_attempt','Counters::publish_returned',
                  'Counters::info_returned','Counters::exceptions','get_subscription_count()',
                  'getTimestamp()','getFrameIndex()','getVideoMode()','reportIR(true)'):
        assert token in s
    assert 'throw; // preserve vendor failure behavior' in s
    assert 'setLaser' not in s and 'setImageRegistrationMode(' not in s
    assert 'Already instrumented; do not reapply' in s

def test_browser_transport_and_render_counters_distinct():
    js=(TOOLS.parents[1]/'web/v2/vision3d.js').read_text()
    assert js.index('browserIr.fetched++') < js.index('drawIr(bytes, response.headers)') < js.index('browserIr.rendered++')
    assert 'browser_ir: browserIr' in js   # page-lifetime scalars only; no image history
