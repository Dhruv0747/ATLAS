"""Read-only, ROS-independent voice telemetry and announcement policy.

Fresh transport is not proof of sensor accuracy or physical action completion.
No function here publishes robot commands or calls a cloud service.
"""
import json
import math
import threading
import time
from collections.abc import Mapping


def as_object(value):
    try:
        result = json.loads(value) if isinstance(value, str) else value
        return result if isinstance(result, dict) else {}
    except (ValueError, TypeError):
        return {}


class FreshValues(Mapping):
    def __init__(self, clock=time.monotonic):
        self.clock = clock
        self.data = {}
        self.lock = threading.RLock()

    @staticmethod
    def ttl(key):
        if key.startswith(('bms_', 'battery_', 'outside_', 'cellular_', 'environment_', 'thermal_')):
            return 20.0
        return 3.0

    def __setitem__(self, key, value):
        with self.lock:
            self.data[key] = (value, self.clock())

    def __getitem__(self, key):
        with self.lock:
            value, stamp = self.data[key]
            if self.clock() - stamp > self.ttl(key):
                raise KeyError(key)
            if isinstance(value, float) and not math.isfinite(value):
                raise KeyError(key)
            return value

    def __iter__(self):
        with self.lock:
            return iter([key for key in self.data if self.get(key) is not None])

    def __len__(self):
        return len(list(iter(self)))

    def age(self, key):
        with self.lock:
            return self.clock() - self.data[key][1] if key in self.data else None

    def bms(self):
        value = as_object(self.get('bms_status'))
        try:
            age = float(value.get('age_s', math.inf))
            soc = float(value.get('soc_percent', math.nan))
            if value.get('ok') is not True or not 0 <= age + (self.age('bms_status') or 0) <= 20 or not 0 <= soc <= 100:
                return {}
        except (TypeError, ValueError):
            return {}
        return value

    def context(self):
        with self.lock:
            return {key: {'value': self[key], 'age_s': round(self.age(key), 2)}
                    for key in list(self) if self.get(key) is not None}


def motion_block(values, enabled=False):
    if not enabled:
        return 'Voice driving is not commissioned. Use the remote; voice cannot bypass safety.'
    policy = as_object(values.get('control_policy'))
    if not policy:
        return 'The control safety status is unavailable.'
    if policy.get('manual_only') is not False:
        return 'ATLAS is in manual-only mode.'
    if policy.get('stop_latched') is not False:
        return 'The remote stop is latched. Reset it using the remote, not voice.'
    if values.get('readiness') != 'AUTO_READY':
        return 'Autonomous readiness has not been confirmed.'
    enc = as_object(values.get('encoder_health'))
    if enc.get('state') not in ('READY', 'HEALTHY') or enc.get('faults'):
        return 'Encoder feedback is not ready.'
    return None


def startup_reply(values, hour, enabled=False):
    period = 'morning' if 5 <= hour < 12 else 'afternoon' if 12 <= hour < 17 else 'evening' if 17 <= hour < 22 else 'night'
    block = motion_block(values, enabled)
    return (f'Good {period}, Dhruv. ATLAS voice is online. '
            + (block or 'The navigation readiness check passes; no motion has been requested.'))


def status_reply(values, question):
    hindi = any('\u0900' <= ch <= '\u097f' for ch in question)
    lower = question.lower()
    if any(word in lower for word in ('battery', 'बैटरी')):
        bms = values.bms()
        if not bms:
            return 'बैटरी की ताज़ा जानकारी उपलब्ध नहीं है।' if hindi else 'Fresh main battery data is unavailable.'
        soc = float(bms['soc_percent'])
        current = bms.get('current_a')
        state = ('charging' if current > .2 else 'discharging' if current < -.2 else 'idle') if isinstance(current, (int, float)) and math.isfinite(current) else 'unknown'
        if hindi:
            states = {'charging': 'चार्ज हो रही है', 'discharging': 'खर्च हो रही है', 'idle': 'लगभग स्थिर है', 'unknown': 'चार्ज स्थिति अज्ञात है'}
            return f'मुख्य बैटरी {soc:.0f} प्रतिशत है, {states[state]}।'
        return f'Main battery is {soc:.0f} percent, {state}. Reading age {values.age("bms_status"):.0f} seconds.'
    if any(word in lower for word in ('gps', 'जीपीएस')):
        fix = values.get('gps_status')
        if fix is None:
            return 'GPS की ताज़ा जानकारी नहीं है।' if hindi else 'GPS data is stale or unavailable.'
        return ('GPS फिक्स उपलब्ध है।' if hindi else 'GPS reports a current fix.') if fix >= 0 else ('GPS जुड़ा है लेकिन फिक्स नहीं है।' if hindi else 'GPS is communicating but has no current fix.')
    if any(word in lower for word in ('temperature', 'तापमान')):
        temp = values.get('outside_temperature_c')
        if temp is None:
            return 'ताज़ा तापमान उपलब्ध नहीं है।' if hindi else 'A fresh environment temperature is unavailable.'
        return f'बाहरी सेंसर का तापमान {temp:.1f} डिग्री सेल्सियस है।' if hindi else f'The outside sensor reads {temp:.1f} degrees Celsius.'
    if any(word in lower for word in ('encoder', 'एन्कोडर')):
        enc = as_object(values.get('encoder_health'))
        if not enc:
            return 'एन्कोडर डेटा पुराना या अनुपलब्ध है।' if hindi else 'Encoder health data is stale or unavailable.'
        if enc.get('state') == 'READY':
            return 'एन्कोडर लिंक चालू है। रुके हुए पहियों से सभी एन्कोडर सही होने का प्रमाण नहीं मिलता।' if hindi else 'Encoder link is ready. Stationary readings do not prove all four encoders work while turning.'
        return f'Encoder report: {enc.get("state", "unknown")}. Faults: {", ".join(enc.get("faults", [])) or "none reported"}.'
    if any(word in lower for word in ('imu', 'आईएमयू')):
        live = values.get('imu_live')
        return ('IM10A डेटा ताज़ा है; नेविगेशन मान्यता अलग परीक्षण है।' if hindi else 'IM10A monitoring messages are fresh; this is not proof of navigation fusion.') if live else ('IM10A डेटा पुराना या अनुपलब्ध है।' if hindi else 'IM10A monitoring data is stale or unavailable.')
    if any(word in lower for word in ('lidar', 'लाइडार')):
        live = values.get('lidar_live')
        return ('लाइडार स्कैन ताज़ा है।' if hindi else 'LiDAR scan messages are fresh; this does not mean every direction is clear.') if live else ('लाइडार डेटा पुराना या अनुपलब्ध है।' if hindi else 'LiDAR scan data is stale or unavailable.')
    if any(word in lower for word in ('sensor', 'सेंसर')):
        expected = {'lidar_live': 'LiDAR', 'imu_live': 'IM10A', 'encoder_health': 'encoder link',
                    'radar_targets': 'radar', 'environment_data': 'environment', 'thermal_data': 'thermal'}
        fresh = [label for key, label in expected.items() if values.get(key) is not None]
        missing = [label for key, label in expected.items() if values.get(key) is None]
        if hindi:
            return f'ताज़ा डेटा: {", ".join(fresh) or "कोई नहीं"}। अनुपलब्ध: {", ".join(missing) or "कोई नहीं"}। डेटा आने से हार्डवेयर सही होने की गारंटी नहीं है।'
        return f'Fresh messages: {", ".join(fresh) or "none"}. Stale or unavailable: {", ".join(missing) or "none"}. Message delivery is not hardware qualification.'
    policy = as_object(values.get('control_policy'))
    reason = policy.get('stop_reason') if policy.get('stop_latched') else values.get('motion_safety')
    mission = values.get('mission_status')
    prefix = 'वर्तमान स्थिति: ' if hindi else 'Current status: '
    if reason:
        if 'joystick unavailable' in str(reason).lower():
            return 'रिमोट का ताज़ा कंट्रोल सिग्नल नहीं है, इसलिए स्टॉप लॉक है। रिमोट और डैशबोर्ड देखें।' if hindi else 'The remote control signal is missing or stale, so the safety stop is latched. Check the remote and dashboard before resetting.'
        if 'B pressed' in str(reason):
            return 'रिमोट का B स्टॉप दबाया गया है। इसे केवल रिमोट से रीसेट करें।' if hindi else 'Remote B latched the stop. Centre the sticks, release buttons, hold LB alone for two seconds and release. Voice cannot reset it.'
        return prefix + str(reason)[:180] + '. ' + ('डैशबोर्ड पर विवरण देखें।' if hindi else 'See the dashboard for details.')
    if mission:
        return prefix + str(mission)[:180]
    return 'सिस्टम की पूरी स्थिति अभी उपलब्ध नहीं है। डैशबोर्ड देखें।' if hindi else 'A complete system readiness report is unavailable. Check the dashboard; I cannot claim everything is healthy.'


def mission_announcement(status):
    # Strict event prefixes from atlas_mission_control. Never infer arrival
    # from a dispatched/accepted goal, or map-save success from a request.
    for prefix, message in (
        ('EXPLORATION ACTIVE ', 'Mapping controller reports exploration active.'),
        ('EXPLORATION STOPPED; MAP ACCEPTED ', 'Mapping controller reports the map saved and accepted.'),
        ('RETURN HOME ACCEPTED', 'Return-home goal accepted. Arrival is not yet confirmed.'),
        ('RETURN HOME VERIFIED ', 'The navigation controller reports return-home verified.'),
        ('RETURN HOME INACCURATE ', 'Return-home accuracy check failed. Please check the dashboard.'),
        ('RETURN HOME REJECTED', 'Return-home goal was rejected.'),
        ('NAVIGATION CANCELED;', 'Navigation controller reports cancellation.'),
        ('NAMED GOAL ACCEPTED ', 'Navigation goal accepted.'),
    ):
        if status.startswith(prefix):
            return message
    return None


class Announcements:
    """Debounced transitions; caller owns bounded queue, playback and TTL."""
    def __init__(self, clock=time.monotonic):
        self.clock = clock
        self.start = clock()
        self.seen = {}
        self.candidate = {}
        self.low = False
        self.full = False

    def transition(self, key, value, delay=2):
        previous, since = self.candidate.get(key, (None, self.clock()))
        if previous != value:
            self.candidate[key] = (value, self.clock())
            return False
        if self.clock() - since < delay or self.seen.get(key) == value:
            return False
        self.seen[key] = value
        return True

    def evaluate(self, values):
        output = []
        if self.clock() - self.start < 15:
            return output
        bms = values.bms()
        if bms:
            soc, current = float(bms['soc_percent']), bms.get('current_a', 0)
            if soc > 25:
                self.low = False
            if soc <= 20 and not self.low:
                output.append(('battery_low', f'Dhruv, main battery is {soc:.0f} percent. Please arrange charging.'))
                self.low = True
            if soc < 95:
                self.full = False
            if soc >= 99 and not self.full and isinstance(current, (int, float)) and 0 <= current < .5:
                # Announce SOC, not proof that the charger completed balancing.
                output.append(('battery_full', 'The BMS reports at least 99 percent charge. Charger completion is not independently verified.'))
                self.full = True
        for key, label in (('encoder_health', 'Encoder health'), ('lidar_live', 'LiDAR'), ('imu_live', 'IMU')):
            # Never announce devices we have never received as newly lost.
            if values.age(key) is None:
                continue
            value = values.get(key)
            state = as_object(value).get('state', 'UNKNOWN') if key == 'encoder_health' and value else ('LIVE' if value else 'STALE')
            if self.transition(key, state) and state in ('CRITICAL', 'DEGRADED', 'STALE'):
                output.append((key, f'{label} reports {state.lower()}. Check the dashboard before driving.'))
        policy = as_object(values.get('control_policy'))
        if policy and self.transition('stop', bool(policy.get('stop_latched'))):
            if policy.get('stop_latched'):
                output.append(('stop', 'Remote safety stop is latched. Check the dashboard. Only the remote can release it.'))
        mission = str(values.get('mission_status', ''))
        if self.transition('mission', mission):
            text = mission_announcement(mission)
            if text:
                output.append(('mission', text))
        return output
