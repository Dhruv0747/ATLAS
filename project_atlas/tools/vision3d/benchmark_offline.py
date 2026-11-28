"""Run one synthetic PC-only 25-second wiring/idle workload, not accuracy test."""
import json
import os
from pathlib import Path
import resource
import subprocess
import sys
import tempfile
import time
import sqlite3
from rtabmap_offline import isolated_env


def main():
    root=Path(__file__).resolve().parent
    out=Path(tempfile.mkdtemp(prefix='atlas-rtabmap-offline-'))
    c=dict(device_serial='synthetic',source='measured_target',independently_validated=True,
           validation_evidence='SYNTHETIC FIXTURE; NO PHYSICAL VALIDATION',width=320,height=240,
           frame_id='test_optical_frame',k=[300.,0.,160.,0.,300.,120.,0.,0.,1.],
           d=[0.]*5,distortion_model='plumb_bob')
    m=dict(serial='synthetic',rgb=c,depth=c,depth_encoding='16UC1',units_to_m=.001,
           scale_verified=True,registered_to_rgb=True,registration_evidence='synthetic',
           tf_evidence='synthetic',tf_at_all_frame_stamps=True,rgb_stamp=10.,depth_stamp=10.,
           info_stamp=10.,odom_stamp=10.,replay_time=10.)
    manifest=out/'synthetic.json'; manifest.write_text(json.dumps(m))
    env=isolated_env()
    start=time.monotonic()
    runner=subprocess.Popen([sys.executable,str(root/'rtabmap_offline.py'),
                             '--manifest',str(manifest),'--output',str(out/'run'),
                             '--seconds','25'],env=env)
    fixture=None
    try:
        time.sleep(3)
        fixture=subprocess.Popen([sys.executable,str(root/'synthetic_rgbd.py')],env=env)
        fixture.wait(timeout=25)
        runner.wait(timeout=12)
    finally:
        for p in (fixture,runner):
            if p is not None and p.poll() is None:
                p.terminate(); p.wait(timeout=8)
    usage=resource.getrusage(resource.RUSAGE_CHILDREN)
    result=dict(evidence=str(out),seconds=time.monotonic()-start,
                aggregate_child_cpu_seconds=usage.ru_utime+usage.ru_stime,
                largest_child_peak_rss_kib=usage.ru_maxrss,
                runner_returncode=runner.returncode,fixture_returncode=fixture.returncode,
                physical_accuracy_verified=False)
    (out/'result.json').write_text(json.dumps(result,indent=2))
    print(json.dumps(result,indent=2))
    if runner.returncode or fixture.returncode: raise SystemExit(1)
    with sqlite3.connect('file:'+str(out/'run/map.db')+'?mode=ro',uri=True) as db:
        assert db.execute('pragma integrity_check').fetchone()[0] == 'ok'
        assert db.execute('select count(*) from Node').fetchone()[0] > 0


if __name__=='__main__': main()
