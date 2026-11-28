"""Offline-testable calibration capture policy and bounded evidence store.

No camera activation entry point. A separately reviewed live adapter must supply
nonblocking local safety observations, original serialized messages, and shutdown.
Raw calibration evidence is allowed without claiming calibrated geometry.
"""
import hashlib
import json
import math
import os
from pathlib import Path
import sqlite3

from calibration_validation import validate_calibration

STREAMS = ('rgb', 'depth', 'rgb_info', 'depth_info')


def number(v):
    if type(v) not in (int, float) or not math.isfinite(v):
        raise ValueError('missing/malformed numeric observation')
    return v


def safety(s, now):
    if not 0 <= number(now)-number(s['received_mono']) <= 1:
        raise ValueError('safety observation stale')
    if not .9 <= number(s['cpu_window_s']) <= 1.1:
        raise ValueError('CPU sample window not one second')
    if not 0 <= number(s['cpu']) < 75 or not 0 <= number(s['ram']) < 80:
        raise ValueError('CPU/RAM admission failed')
    if not 0 < number(s['temperature']) < 70:
        raise ValueError('temperature unavailable/over limit')
    for name, expected in [('estop',True),('manual_only',True),('commissioning',False),
                           ('recorder_off',True),('telemetry_live',True)]:
        if s[name] is not expected:
            raise ValueError(name+' failed')
    if not 0 <= number(s['telemetry_age']) <= 1:
        raise ValueError('telemetry stale')
    if any(number(s[k]) != 0 for k in ('linear','angular')):
        raise ValueError('nonzero command')
    if len(s['encoder_deltas']) != 4 or any(number(v) != 0 for v in s['encoder_deltas']):
        raise ValueError('encoder movement/unknown')


def stamp_ns(meta):
    sec, ns = meta['stamp_sec'], meta['stamp_nanosec']
    if type(sec) is not int or type(ns) is not int or sec < 0 or not 0 <= ns < 1000000000:
        raise ValueError('malformed source timestamp')
    return sec*1000000000+ns


def bundle(messages, source_now_ns, expected):
    if set(messages) != set(STREAMS):
        raise ValueError('missing stream')
    stamps=[]
    for name in STREAMS:
        m=messages[name]; stamp=stamp_ns(m); stamps.append(stamp)
        if not 0 <= source_now_ns-stamp <= 500000000:
            raise ValueError('stale/future source frame')
        if (m['width'],m['height'],m['frame_id']) != tuple(expected[name]):
            raise ValueError('unexpected dimensions/frame')
        if not isinstance(m['cdr'],bytes) or not m['cdr']:
            raise ValueError('original serialized payload required')
        if name in ('rgb','depth'):
            bpp={'rgb8':3,'bgr8':3} if name=='rgb' else {'16UC1':2,'32FC1':4}
            if m['encoding'] not in bpp:
                raise ValueError('unsupported encoding')
            if m['step'] < m['width']*bpp[m['encoding']] or m['data_bytes'] != m['step']*m['height']:
                raise ValueError('malformed image layout')
            if name=='depth' and m['units_to_m'] != (.001 if m['encoding']=='16UC1' else 1.):
                raise ValueError('unexpected depth units')
        else:
            if len(m['k']) != 9 or not all(math.isfinite(number(v)) for v in m['k']):
                raise ValueError('CameraInfo invalid')
            if m['k'][0] <= 0 or m['k'][4] <= 0:
                raise ValueError('CameraInfo uncalibrated')
    if max(stamps)-min(stamps)>30000000:
        raise ValueError('RGB-D skew exceeds 30ms')
    return tuple(stamps)


class Evidence:
    """SQLite payloads retain original CDR, integer stamps and SHA256.

    SQLite max_page_count enforces DB page limit; rollback journal may consume a
    further database-sized allocation. Reserve 1GiB free in the live adapter.
    """
    def __init__(self, directory, max_bytes=128*1024**2):
        self.path=Path(directory); self.path.mkdir(parents=True,exist_ok=False)
        self.db=sqlite3.connect(self.path/'capture.sqlite')
        self.db.execute('pragma journal_mode=DELETE')
        self.db.execute('pragma synchronous=FULL')
        page=self.db.execute('pragma page_size').fetchone()[0]
        self.db.execute('pragma max_page_count='+str(max(4,max_bytes//page)))
        self.db.execute('create table messages(id integer primary key, stream text, stamp_ns integer, metadata text, sha256 text, cdr blob)')
        self.db.commit()

    def write(self, messages):
        with self.db:
            for name,m in messages.items():
                metadata={k:v for k,v in m.items() if k!='cdr'}
                self.db.execute('insert into messages(stream,stamp_ns,metadata,sha256,cdr) values(?,?,?,?,?)',
                    (name,stamp_ns(m),json.dumps(metadata,allow_nan=False),hashlib.sha256(m['cdr']).hexdigest(),m['cdr']))

    def finish(self, result):
        try:
            self.db.commit()
            result['sqlite_integrity']=self.db.execute('pragma integrity_check').fetchone()[0]
        finally:
            self.db.close()
        result['database_sha256']=hashlib.sha256((self.path/'capture.sqlite').read_bytes()).hexdigest()
        temp=self.path/'result.tmp'
        with temp.open('x') as f:
            json.dump(result,f,allow_nan=False,indent=2); f.flush(); os.fsync(f.fileno())
        os.replace(temp,self.path/'result.json')


class Supervisor:
    """Tick from a nonblocking 10Hz supervisor; independent runtime lease required.

    No Start action exists here. Duration includes prelaunch work, from admission.
    A stalled or crashed process must be stopped by the existing runtime lease,
    not by a Python finally block. Tick tests cannot prove that hardware contract.
    """
    def __init__(self, now, store, stop, expected, calibration=None, serial=''):
        self.start=now; self.last_tick=now; self.last_safety=None; self.last_bundle=None
        self.last_stamps=None; self.store=store; self.stop=stop; self.expected=expected
        self.closed=False; self.count=0; self.calibration_status='UNVALIDATED'
        if calibration is not None:
            for name in ('rgb','depth'):
                w,h,f=expected[name]
                validate_calibration(calibration[name],serial,w,h,f)
            self.calibration_status='DOCUMENT_VALID_PHYSICAL_ACCURACY_NOT_PROVEN'

    def tick(self, now, observation, messages=None, source_now_ns=None):
        if self.closed: raise RuntimeError('single use capture already closed')
        try:
            if now < self.last_tick or now-self.last_tick>1:
                raise ValueError('supervision deadline missed')
            self.last_tick=now
            safety(observation,now)
            if now-self.start>=60:
                return self.close('COMPLETE' if self.count else 'ABORTED','60-second deadline')
            if messages is not None:
                stamps=bundle(messages,source_now_ns,self.expected)
                if self.last_stamps is not None and any(a<=b for a,b in zip(stamps,self.last_stamps)):
                    raise ValueError('duplicate/regressing frame stamps')
                self.store.write(messages); self.count+=1
                self.last_stamps=stamps; self.last_bundle=now
            if self.last_bundle is None and now-self.start>=10:
                raise ValueError('no complete RGB-D bundle within 10 seconds')
            if self.last_bundle is not None and now-self.last_bundle>1:
                raise ValueError('stream delivery stale')
        except Exception as exc:
            self.close('ABORTED',str(exc))

    def close(self, status, reason):
        if self.closed: return
        self.closed=True
        result=dict(status=status,reason=reason,bundles=self.count,calibration=self.calibration_status)
        try:
            if self.stop() is not True:
                raise RuntimeError('camera shutdown not verified')
            result['shutdown_verified']=True
        except Exception as exc:
            result.update(status='ABORTED',shutdown_verified=False,cleanup_error=str(exc))
        self.store.finish(result)
        return result
