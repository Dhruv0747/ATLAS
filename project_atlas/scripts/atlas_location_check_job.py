"""Read-only manual-location job lifecycle. No ROS publishers or reseeding.

Candidate foundation: a trusted ROS adapter must supply evidence snapshots and
call checkpoint throughout the existing matcher. Not a deployed HTTP endpoint.
Timeout/cancel does NOT release the worker slot until finish acknowledges exit.
"""
from copy import deepcopy
import math
import threading
import time
import uuid


class CheckAborted(RuntimeError):
    pass


def evidence_error(evidence):
    """Reject absent evidence. Age thresholds reuse the existing parked monitor.

coverage_qualified and tf_chain_consistent must come from a validated adapter,
never a browser request. A missing qualifier is not implicitly true.
"""
    if not isinstance(evidence, dict):
        return 'evidence unavailable'
    for key, maximum in (('scan_age_s', 1.), ('scan_receipt_age_s', 1.),
                         ('odom_age_s', 1.), ('imu_age_s', 1.), ('amcl_age_s', 2.5)):
        value=evidence.get(key)
        if type(value) not in (int,float) or not math.isfinite(value) or not 0 <= value <= maximum:
            return key+' unavailable or stale'
    if not evidence.get('map_id') or evidence.get('map_id') != evidence.get('loaded_map_id'):
        return 'accepted map and loaded map do not match'
    for key in ('stationary_epoch','localization_epoch','scan_stamp'):
        if evidence.get(key) is None:
            return key+' missing'
    stamp=evidence['scan_stamp']
    if type(stamp) not in (int,float) or not math.isfinite(stamp) or stamp <= 0:
        return 'scan timestamp invalid'
    for key in ('stationary','stop_latched','commands_zero','tf_at_scan',
                'tf_chain_consistent','coverage_qualified'):
        if evidence.get(key) is not True:
            return key+' not confirmed'
    pose=evidence.get('amcl_pose')
    if not isinstance(pose,(list,tuple)) or len(pose)!=3 or not all(
        type(v) in (int,float) and math.isfinite(v) for v in pose):
        return 'AMCL reference invalid'
    return None


class LocationCheckJob:
    def __init__(self, timeout_s=30., clock=time.monotonic, wall=time.time):
        if not 0 < timeout_s <= 30:
            raise ValueError('timeout must be within 30 seconds')
        self.timeout_s=timeout_s; self.clock=clock; self.wall=wall
        self.lock=threading.RLock(); self.worker_id=None; self.job=None

    def start(self, evidence):
        with self.lock:
            if self.worker_id is not None:
                raise ValueError('verification worker still active')
            error=evidence_error(evidence)
            if error:
                raise ValueError(error)
            request_id=uuid.uuid4().hex
            self.worker_id=request_id
            self.job=dict(request_id=request_id,state='CHECKING',started_unix=self.wall(),
                          started_mono=self.clock(),evidence=deepcopy(evidence),
                          navigation_authorized=False,correction_enabled=False)
            return request_id

    def _end(self, state, reason):
        self.job.update(state=state,reason=reason,ended_unix=self.wall(),
                        calculation_s=self.clock()-self.job['started_mono'])

    def checkpoint(self, request_id, evidence=None):
        with self.lock:
            if self.job is None or self.job['request_id'] != request_id or self.worker_id != request_id:
                raise CheckAborted('obsolete worker')
            if self.job['state'] != 'CHECKING':
                raise CheckAborted(self.job.get('reason',self.job['state']))
            if self.clock()-self.job['started_mono'] >= self.timeout_s:
                self._end('TIMED_OUT','bounded search deadline exceeded')
                raise CheckAborted('deadline exceeded')
            if evidence is not None:
                error=evidence_error(evidence)
                start=self.job['evidence']
                for key in ('map_id','stationary_epoch','localization_epoch'):
                    if evidence.get(key) != start[key]:
                        error=key+' changed during verification'
                if not error:
                    before,now=start['amcl_pose'],evidence['amcl_pose']
                    dyaw=abs(math.atan2(math.sin(now[2]-before[2]),math.cos(now[2]-before[2])))
                    if math.hypot(now[0]-before[0],now[1]-before[1]) > .10 or dyaw > math.radians(3.):
                        error='AMCL reference changed during verification'
                if error:
                    self._end('STALE',error)
                    raise CheckAborted(error)

    def cancel(self, request_id):
        with self.lock:
            if self.job is None or self.job['request_id'] != request_id:
                raise ValueError('request id mismatch')
            if self.job['state']=='CHECKING':
                self._end('CANCELLED','operator cancelled')

    def finish(self, request_id, result=None, evidence=None, error=None):
        with self.lock:
            if self.worker_id != request_id:
                return False
            try:
                self.checkpoint(request_id,evidence)
                if error or evidence is None or result is None:
                    self._end('UNCERTAIN',str(error or 'missing final evidence/result'))
                    return False
                state=result.get('state')
                if state not in ('VERIFIED','MISMATCH','UNCERTAIN','LOST','STALE'):
                    self._end('UNCERTAIN','unsupported matcher result')
                    return False
                self._end(state,result.get('reason',''))
                self.job['result']=deepcopy(result)
                self.job['final_evidence']=deepcopy(evidence)
                return True
            except CheckAborted:
                return False
            finally:
                self.worker_id=None

    def snapshot(self):
        with self.lock:
            if self.worker_id is not None:
                try:
                    self.checkpoint(self.worker_id)
                except CheckAborted:
                    pass
            result=deepcopy(self.job or dict(state='IDLE',navigation_authorized=False,
                                              correction_enabled=False))
            # A completed check is a timestamped observation, never a live
            # navigation authorization or indefinitely fresh startup verdict.
            result['historical_result']=result['state'] not in ('IDLE','CHECKING')
            if 'ended_unix' in result:
                result['result_age_s']=max(0.,self.wall()-result['ended_unix'])
            return result
