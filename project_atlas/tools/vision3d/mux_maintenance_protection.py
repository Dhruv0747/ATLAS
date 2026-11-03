"""Independent maintenance protection for the Mux transaction window.

While the Mux restarts, its policy and command evidence (and E-STOP arbitration through the
Mux) disappear, and Recovery/HTTP observers of those same topics cannot vouch for the rover.
Protection must therefore be independent of the Mux. The only accepted form is electrically
verified actuator isolation, recorded as measured evidence and approved by the owner by SHA256.

- Unavailable (the default) always refuses, with the original message.
- AttestedIsolation accepts only complete, measured, boot-bound evidence whose validity covers
  the whole 90 s transaction (60 s worker + 30 s cleanup), including automatic restarts of the
  Restart=always/on-failure services.
- Owner confirmation of disconnection is recorded but is never sufficient on its own.
- A photograph or a single 0 V reading is not accepted: every actuator output needs a measurement
  with the board powered both from the battery and from USB only, plus an explicit USB-backfeed check.

This is evidence of a physical lockout state, not live sensing. Reconnecting an actuator during
the window is outside what software can detect; the lockout procedure must prevent it.
"""
import hashlib
import json
import math

SCHEMA = 'atlas-mux-isolation-evidence/1'
ACTUATORS = {'M1', 'M2', 'M3', 'M4', 'S1', 'S2'}
REQUIRED_SUPPLIES = {'battery_dcdc', 'jetson_usb_5v'}
AUTO_RESTART_UNITS = {'atlas-cmd-vel-mux.service', 'atlas-sensor-recovery.service',
                      'rover-status-web.service', 'rover-base-telemetry.service'}
MAX_OPEN_VOLTS = 0.2
KEYS = {'schema', 'boot_id', 'valid_from_boottime', 'valid_until_boottime', 'actuators',
        'supply_paths', 'usb_backfeed', 'auto_restart_units', 'owner_confirmation',
        'electrical_verification'}
UNAVAILABLE = 'verified independent maintenance protection unavailable'


def require(condition, reason):
    if not condition:
        raise ValueError(reason)


def finite(value):
    return type(value) in (int, float) and math.isfinite(value)


class Unavailable:
    def verify(self, now, boot):
        raise ValueError(UNAVAILABLE)


class AttestedIsolation:
    def __init__(self, data, approved, boot, window_end):
        require(isinstance(approved, str) and len(approved) == 64 and all(c in '0123456789abcdef' for c in approved)
                and hashlib.sha256(data).hexdigest() == approved, UNAVAILABLE + ': evidence not owner-approved')
        e = json.loads(data)
        require(isinstance(e, dict) and set(e) == KEYS and e['schema'] == SCHEMA, UNAVAILABLE + ': evidence schema')
        require(e['boot_id'] == boot, UNAVAILABLE + ': evidence for another boot')
        start, until = e['valid_from_boottime'], e['valid_until_boottime']
        require(finite(start) and finite(until) and 0 <= start < until and finite(window_end)
                and until >= window_end, UNAVAILABLE + ': evidence does not cover the whole transaction window')
        verification = e['electrical_verification']
        require(isinstance(verification, dict) and verification.get('method') == 'measured'
                and all(isinstance(verification.get(k), str) and verification[k].strip()
                        for k in ('instrument', 'measured_by')),
                UNAVAILABLE + ': owner confirmation alone is not electrical verification')
        actuators = e['actuators']
        require(isinstance(actuators, dict) and set(actuators) == ACTUATORS, UNAVAILABLE + ': actuator set')
        for name, row in actuators.items():
            require(isinstance(row, dict) and row.get('connector_open') is True, UNAVAILABLE + ': ' + name + ' connected')
            for mode in ('battery_powered', 'usb_only'):
                m = row.get(mode)
                require(isinstance(m, dict) and finite(m.get('volts')) and abs(m['volts']) <= MAX_OPEN_VOLTS
                        and m.get('pwm_detected') is False, UNAVAILABLE + ': ' + name + ' not measured dead (' + mode + ')')
        supplies = e['supply_paths']
        require(isinstance(supplies, dict) and REQUIRED_SUPPLIES <= set(supplies)
                and all(isinstance(v, dict) and v.get('isolated') is True and isinstance(v.get('method'), str)
                        and v['method'].strip() for v in supplies.values()), UNAVAILABLE + ': supply-path inventory')
        backfeed = e['usb_backfeed']
        require(isinstance(backfeed, dict) and backfeed.get('checked') is True
                and type(backfeed.get('mcu_alive_on_usb')) is bool and backfeed.get('outputs_open') is True,
                UNAVAILABLE + ': USB backfeed not verified')
        require(isinstance(e['auto_restart_units'], list) and AUTO_RESTART_UNITS <= set(e['auto_restart_units']),
                UNAVAILABLE + ': automatic restarts not covered')
        self.boot, self.start, self.until = boot, start, until

    def verify(self, now, boot):
        require(boot == self.boot and finite(now) and self.start <= now <= self.until,
                UNAVAILABLE + ': evidence expired or boot changed')
