"""No camera activation: distinguish driver lifecycle from delivered frame evidence."""
import sys
from pathlib import Path
from unittest.mock import patch,MagicMock
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
import atlas_vision3d_web as W
import atlas_vision3d_runtime as R
from test_vision3d_stage32_ir import ir_msg

def test_driver_running_does_not_prove_frames():
    s=W.VisionService({'viewer_runtime':True})
    with patch.object(R.SESSION,'status',return_value={'state':'ACTIVE','mode':'ir','driver_pid':123}):
        st=s.status()
    assert st['ir_delivery']=='IR NO FRAMES RECEIVED'
    assert st['ir_boundaries']['receiver_callbacks']==0
    assert st['ir_boundaries']['sensor_frame_received'].startswith('UNKNOWN')
    assert st['ir_boundaries']['ros_frame_published']=='UNKNOWN'

def test_final_scalar_counts_survive_stop_without_images():
    s=W.VisionService({'topics':{'ir':'/astra/ir/image_raw'}},clock=lambda:100,wall=lambda:100)
    s.ingest('ir',ir_msg());s.stop()
    st=s.status()
    assert st['last_session']['streams']['ir']['received']==1
    assert not s.messages and not s.cache and not s.stats
    assert st['streams']['ir']['received']==0

def test_snapshot_failure_cannot_prevent_stop():
    s=W.VisionService({});t=MagicMock();s.transport=t
    with patch.object(s,'status',side_effect=ValueError('bad metadata')):s.stop()
    t.stop.assert_called_once();assert s.transport is None
    assert s.last_session['capture_error']=='bad metadata'

def test_stale_distinguished_from_no_frames():
    now=[100.0];s=W.VisionService({'viewer_runtime':True},clock=lambda:now[0],wall=lambda:now[0])
    with patch.object(R.SESSION,'status',return_value={'state':'ACTIVE','mode':'ir','driver_pid':123}):
        s.ingest('ir',ir_msg());assert s.status()['ir_delivery']=='IR FRAMES RECEIVED'
        now[0]=103;assert s.status()['ir_delivery']=='IR STREAM STALE'

def test_browser_no_frames_label_and_strict_native_encoding():
    js=(Path(__file__).resolve().parents[1]/'web/v2/vision3d.js').read_text()
    state=(Path(__file__).resolve().parents[1]/'web/v2/vision3d_state.js').read_text()
    assert "'No frames received'" in state and "label: 'Waiting for frames'" in state   # Stage32 UI fix wording
    assert "['mono8', 'mono16', '16UC1'].includes(enc)" in js
    assert 'browserIr.rendered++' in js

def test_api_prepared_is_not_browser_delivery_and_survives_stop():
    s=W.VisionService({},clock=lambda:100,wall=lambda:100)
    s.ingest('ir',ir_msg());s.raw('ir');s.raw('ir')
    assert s.status()['ir_api']['responses_prepared']==2
    assert s.status()['ir_api']['unique_stamps']==1
    s.stop()
    assert s.status()['last_session']['ir_api']['responses_prepared']==2
    assert s.status()['ir_api']['responses_prepared']==0
