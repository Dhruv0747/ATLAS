"""Offline adapter candidate for an EXISTING ROS subscriber's observations.

No ROS imports, subscribers, threads or background loop. Not integrated/deployed.
Producer exports raw receipt times; consumer applies the same stationary gates.
"""
import json
import copy
import os
from pathlib import Path
from restart_safety_observer import Safety


def publish(path,values,now,boot_id):
    # Caller supplies existing callback values/timestamps. Never refresh their age.
    payload={'boot_id':boot_id,'published_mono':now,'observations':values}
    raw=json.dumps(payload,allow_nan=False,separators=(',',':')).encode()
    if len(raw)>16384:raise ValueError('safety snapshot too large')
    path=Path(path);temp=path.with_suffix('.tmp')
    fd=os.open(temp,os.O_WRONLY|os.O_CREAT|os.O_TRUNC|os.O_NOFOLLOW,0o600)
    with os.fdopen(fd,'wb') as f:f.write(raw);f.flush()
    os.replace(temp,path)


def verify(path,now,boot_id):
    with Path(path).open('rb') as f:raw=f.read(16385)
    if len(raw)>16384:raise ValueError('oversized snapshot')
    data=json.loads(raw)
    if data['boot_id']!=boot_id or not 0<=now-data['published_mono']<=.75:raise ValueError('wrong boot/stale producer')
    state=Safety()
    for key,item in data['observations'].items():
        if key not in ('policy','command','encoders') or len(item)!=2:raise ValueError('invalid observation')
        state.receive(key,item[0],item[1])
    encoder = data['observations'].get('encoders', [None])[0]
    if isinstance(encoder, dict) and 'encoder_packet_monotonic' in encoder:
        packet = encoder['encoder_packet_monotonic']
        if not SourceConsumer.finite(packet) or not 0 <= now-packet <= 1:
            raise ValueError('raw encoder packet expired')
    result=state.evaluate(now)
    if not result['safe']:raise ValueError(result['reason'])
    return result


class Producer:
    """Opt-in export from existing callbacks; no ROS entity or background task."""
    def __init__(self, path, boot_id):
        self.path = Path(path)
        self.boot_id = boot_id
        self.values = {}
        self.last_write = float('-inf')
        self.failed = False

    def receive(self, key, value, now):
        if self.failed:
            return
        self.values[key] = [value, now]
        if now - self.last_write < .1:
            return
        try:
            publish(self.path, self.values, now, self.boot_id)
            self.last_write = now
        except Exception:
            # Never disturb recovery callbacks; stale cache rejects the consumer.
            self.failed = True
            try:
                self.path.unlink(missing_ok=True)
            except OSError:
                pass


class Consumer:
    """Session-latched rejection, including failures before admission."""
    def __init__(self, path, boot_id):
        import threading
        self.path, self.boot_id = path, boot_id
        self.failure = None
        self.lock = threading.Lock()

    def check(self, now):
        with self.lock:
            if self.failure is not None:
                raise ValueError(self.failure)
            try:
                return verify(self.path, now, self.boot_id)
            except Exception as exc:
                self.failure = str(exc)
                raise


class SourceConsumer:
    """Opt-in source-time validator; no transport, ROS node or receipt-time fallback.

    identities must be independently verified (boot_id, pid, start_ticks), not
    learned from the first network message. A disconnect permanently closes session.
    Unstamped /cmd_vel is not authority; its exact publication is carried in policy.
    """
    def __init__(self, boot_id, identities):
        self.boot_id = boot_id
        self.identities = dict(identities)
        self.latest = {}
        self.failure = None
        self.command = None

    def disconnect(self):
        self.failure = 'source disconnected'

    @staticmethod
    def finite(value):
        import math
        return type(value) in (int, float) and math.isfinite(value)

    def receive(self, key, payload, now):
        if self.failure: raise ValueError(self.failure)
        try:
            if key not in ('policy', 'encoders') or not self.finite(now):
                raise ValueError('invalid source')
            payload = copy.deepcopy(payload)
            p = payload['source_provenance']
            if type(p['pid']) is not int or p['pid'] <= 0 or type(p['start_ticks']) is not int or p['start_ticks'] < 0:
                raise ValueError('invalid process identity')
            identity = (p['boot_id'], p['pid'], p['start_ticks'])
            if identity != self.identities[key] or p['boot_id'] != self.boot_id:
                raise ValueError('source identity changed')
            stamp, seq = p['observed_mono'], p['sequence']
            if not self.finite(stamp) or not 0 <= now-stamp <= 1:
                raise ValueError('source stale/future')
            if type(seq) is not int or seq <= 0:
                raise ValueError('invalid source sequence')
            previous = self.latest.get(key)
            if previous and (seq <= previous[0] or stamp <= previous[1]):
                raise ValueError('source replay/out of order')
            if key == 'policy':
                cmd = payload['published_command']
                cs, ct = cmd['sequence'], cmd['published_mono']
                if type(cs) is not int or cs <= 0 or not self.finite(ct) or not 0 <= stamp-ct or not 0 <= now-ct <= 1:
                    raise ValueError('command provenance stale/invalid')
                if self.command:
                    if cs < self.command['sequence'] or ct < self.command['published_mono']:
                        raise ValueError('command replay')
                    if cs == self.command['sequence'] and cmd != self.command:
                        raise ValueError('command sequence reused')
                    if cs > self.command['sequence'] and ct <= self.command['published_mono']:
                        raise ValueError('command time did not advance')
                self.command = dict(cmd)
            else:
                packet, age = payload['encoder_packet_monotonic'], payload['packet_age_s']
                update_seq = payload['encoder_update_sequence']
                if type(update_seq) is not int or update_seq < 0:
                    raise ValueError('invalid encoder update sequence')
                if previous and (packet < previous[2]['encoder_packet_monotonic'] or update_seq < previous[2]['encoder_update_sequence']):
                    raise ValueError('encoder source regressed')
                if not self.finite(packet) or packet <= 0 or not 0 <= now-packet <= 1:
                    raise ValueError('encoder packet stale/invalid')
                if not self.finite(age) or age < 0 or packet > stamp or age+now-stamp > 1:
                    raise ValueError('combined encoder age')
                # Existing packet_age_s is rounded to milliseconds. Use raw time
                # for enforcement; this tolerance only checks representation.
                if abs((stamp-packet)-age) > .000501:
                    raise ValueError('encoder age inconsistent')
            self.latest[key] = (seq, stamp, payload)
        except (KeyError, TypeError, ValueError, AttributeError) as exc:
            self.failure = str(exc)
            raise ValueError(self.failure) from exc

    def check(self, now, output_mono):
        if self.failure: raise ValueError(self.failure)
        try:
            if not self.finite(now) or not self.finite(output_mono) or not 0 <= now-output_mono <= .75:
                raise ValueError('observer output stale')
            safety = Safety()
            for key in ('policy', 'encoders'):
                _, stamp, payload = self.latest[key]
                if not 0 <= now-stamp <= 1: raise ValueError('source expired')
                safety.receive(key, payload, stamp)
            cmd = self.latest['policy'][2]['published_command']
            safety.receive('command', cmd['values'], cmd['published_mono'])
            enc = self.latest['encoders'][2]
            if now-enc['encoder_packet_monotonic'] > 1: raise ValueError('encoder packet expired')
            result = safety.evaluate(now)
            if not result['safe']: raise ValueError(result['reason'])
            return result
        except (KeyError, TypeError, ValueError, AttributeError) as exc:
            self.failure = str(exc)
            raise ValueError(self.failure) from exc
