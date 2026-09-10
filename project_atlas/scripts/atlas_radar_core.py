"""Deterministic RD-03D parsing, odom-frame tracking and advisory risk model.

No ROS dependencies or actuator access. SI units except raw UART fields.
Track IDs are short-lived associations, never person identities.
"""
import itertools
import math
import struct
from dataclasses import dataclass

HEADER = bytes.fromhex('AA FF 03 00')
TAIL = bytes.fromhex('55 CC')
CONFIG_HEADER = bytes.fromhex('FD FC FB FA')
CONFIG_TAIL = bytes.fromhex('04 03 02 01')
ENABLE_CONFIG = bytes.fromhex('FD FC FB FA 04 00 FF 00 01 00 04 03 02 01')
QUERY_VERSION = bytes.fromhex('FD FC FB FA 02 00 00 00 04 03 02 01')
MULTI_TARGET = bytes.fromhex('FD FC FB FA 02 00 90 00 04 03 02 01')
END_CONFIG = bytes.fromhex('FD FC FB FA 02 00 FE 00 04 03 02 01')


def signed(raw):
    return (raw & 0x7fff) * (1 if raw & 0x8000 else -1)


class Decoder:
    def __init__(self):
        self.buffer = b''
        self.bad = 0
        self.discarded = 0
        self.acks = []

    def feed(self, data):
        self.buffer += data
        output = []
        while len(self.buffer) >= 4:
            starts = [i for i in (self.buffer.find(HEADER), self.buffer.find(CONFIG_HEADER)) if i >= 0]
            if not starts:
                self.discarded += max(0, len(self.buffer) - 3)
                self.buffer = self.buffer[-3:]
                break
            first = min(starts)
            self.discarded += first
            self.buffer = self.buffer[first:]
            config = self.buffer.startswith(CONFIG_HEADER)
            if config and len(self.buffer) < 6:
                break
            length = 10 + int.from_bytes(self.buffer[4:6], 'little') if config else 30
            if length > 256 or length < (14 if config else 30):
                self.bad += 1
                self.buffer = self.buffer[1:]
                continue
            if len(self.buffer) < length:
                break
            frame = self.buffer[:length]
            if not frame.endswith(CONFIG_TAIL if config else TAIL):
                self.bad += 1
                self.buffer = self.buffer[1:]
                continue
            self.buffer = self.buffer[length:]
            if config:
                self.acks.append({'command': int.from_bytes(frame[6:8], 'little'),
                                  'status': int.from_bytes(frame[8:10], 'little'),
                                  'payload_hex': frame[10:-4].hex()})
                self.acks = self.acks[-16:]
                continue
            targets = []
            for slot, offset in enumerate((4, 12, 20), 1):
                fields = struct.unpack_from('<4H', frame, offset)
                if not any(fields):
                    continue
                x, y, speed = [signed(v) for v in fields[:3]]
                distance = math.hypot(x, y) / 1000
                if y <= 0 or not 0.05 <= distance <= 8.5 or abs(speed) > 1000:
                    self.bad += 1
                    continue
                targets.append({'slot': slot, 'x_mm': x, 'y_mm': y,
                                'speed_cm_s': speed, 'resolution_mm': fields[3]})
            output.append(targets)
        return output


def rotate(x, y, yaw):
    c, s = math.cos(yaw), math.sin(yaw)
    return c*x - s*y, s*x + c*y


def base_point(target, cfg):
    # Manufacturer sensor coordinates: X right, Y forward (installation
    # convention MUST be confirmed physically). ROS base: X forward, Y left.
    x, y = rotate(target['y_mm']/1000, -target['x_mm']/1000,
                  cfg.get('radar_yaw_rad', 0.0))
    return x + cfg.get('radar_x_m', 0.0), y + cfg.get('radar_y_m', 0.0)


@dataclass
class Track:
    id: int
    x: float
    y: float
    at: float
    vx: float = 0.0
    vy: float = 0.0
    hits: int = 1
    slot: int = 0
    radial: float = 0.0
    world_radial: float = 0.0
    ambiguous: bool = False
    camera_at: float = -1e9
    lidar_at: float = -1e9


class Tracker:
    def __init__(self, cfg):
        self.cfg = cfg
        self.tracks = []
        self.next_id = 1
        self.last_pose = None
        self.last_frame = -1e9

    def clear(self):
        self.tracks.clear()
        self.last_pose = None

    def update(self, targets, at, pose, velocity):
        if at <= self.last_frame:
            return
        if self.last_pose:
            px, py, pyaw, pt = self.last_pose
            dt = at - pt
            yaw_delta = abs(math.atan2(math.sin(pose[2]-pyaw), math.cos(pose[2]-pyaw)))
            if math.hypot(pose[0]-px, pose[1]-py) > 0.2 + 1.0*dt or yaw_delta > 0.2 + 2.0*dt:
                self.clear()
        self.last_pose = (*pose, at)
        self.last_frame = at
        self.tracks = [t for t in self.tracks if at-t.at <= self.cfg['track_timeout_s']]
        points = []
        for target in targets[:3]:
            bx, by = base_point(target, self.cfg)
            wx, wy = rotate(bx, by, pose[2])
            points.append((wx+pose[0], wy+pose[1], bx, by, target))
        # Exhaustive assignment is small (<= 3 detections), deterministic and
        # independent of the device's slot order. Unmatched observations cost
        # the gate distance. No two detections can claim the same track.
        gate = self.cfg['association_gate_m']
        costs = []
        for t in self.tracks:
            dt = at-t.at
            costs.append([math.hypot(p[0]-t.x-t.vx*dt, p[1]-t.y-t.vy*dt) for p in points])
        best = (float('inf'), ())
        for assignment in itertools.product(range(-1, len(self.tracks)), repeat=len(points)):
            used = [v for v in assignment if v >= 0]
            if len(set(used)) != len(used):
                continue
            cost = sum(gate if j < 0 else costs[j][i] for i, j in enumerate(assignment))
            if any(j >= 0 and costs[j][i] >= gate for i, j in enumerate(assignment)):
                continue
            if cost < best[0]:
                best = cost, assignment
        additions = []
        for i, (wx, wy, bx, by, target) in enumerate(points):
            j = best[1][i]
            ambiguous = sum(row[i] < gate*0.6 for row in costs) > 1
            if j < 0:
                t = Track(self.next_id, wx, wy, at)
                self.next_id += 1
                additions.append(t)
            else:
                t = self.tracks[j]
                dt = max(0.02, at-t.at)
                rx, ry = wx-(t.x+t.vx*dt), wy-(t.y+t.vy*dt)
                t.x += t.vx*dt + 0.65*rx
                t.y += t.vy*dt + 0.65*ry
                t.vx = max(-3., min(3., t.vx + 0.15*rx/dt))
                t.vy = max(-3., min(3., t.vy + 0.15*ry/dt))
                t.at, t.hits = at, t.hits+1
            t.slot, t.radial, t.ambiguous = target['slot'], target['speed_cm_s']/100, ambiguous
            if ambiguous:
                t.camera_at = -1e9
            sx, sy = self.cfg.get('radar_x_m', 0), self.cfg.get('radar_y_m', 0)
            dx, dy = bx-sx, by-sy
            norm = max(0.05, math.hypot(dx, dy))
            # v_sensor = v_base + omega cross radar lever arm. Radar speed is
            # relative radial speed; this produces only WORLD RADIAL speed,
            # never claims that Doppler supplies a full 2D velocity vector.
            t.world_radial = t.radial + ((velocity[0]-velocity[2]*sy)*dx +
                                        (velocity[1]+velocity[2]*sx)*dy)/norm
        self.tracks.extend(additions)

    def snapshot(self, now, pose):
        self.tracks = [t for t in self.tracks if now-t.at <= self.cfg['track_timeout_s']]
        result = []
        for t in self.tracks:
            age = max(0., now-t.at)
            bx, by = rotate(t.x+t.vx*age-pose[0], t.y+t.vy*age-pose[1], -pose[2])
            vx, vy = rotate(t.vx, t.vy, -pose[2])
            confidence = min(0.95, 0.25+t.hits*0.12) * max(0., 1-age/self.cfg['track_timeout_s'])
            if t.ambiguous:
                confidence *= 0.5
            result.append({'track_id': t.id, 'slot': t.slot, 'x_m': bx, 'y_m': by,
                           'distance_m': math.hypot(bx, by), 'vx_mps': vx, 'vy_mps': vy,
                           'relative_radial_mps': t.radial, 'world_radial_mps': t.world_radial,
                           'age_s': age, 'confidence': confidence,
                           'ambiguous': t.ambiguous, 'hits': t.hits,
                           'person_confirmed': now-t.camera_at <= self.cfg['camera_timeout_s'] and not t.ambiguous,
                           'camera_age_s': min(999., now-t.camera_at),
                           'lidar_confirmed': now-t.lidar_at <= self.cfg['fusion_timeout_s']})
        return result


def risk(tracks, speed, yaw_rate, cfg):
    """Conservative bounded constant-curvature sweep with moving targets.

    Caps are advisory until real brake/footprint/extrinsic validation. A close
    single-frame return still constrains speed even before track confirmation.
    """
    v = abs(speed)
    reaction, decel = cfg['reaction_s'], cfg['decel_mps2']
    if not math.isfinite(decel) or decel <= 0:
        return {'scale': 0., 'reason': 'INVALID_BRAKING_CONFIG'}
    braking = v*reaction + v*v/(2*decel)
    horizon = max(cfg['prediction_s'], reaction+v/decel)
    direction = 1 if speed >= 0 else -1
    scale, reason, hazard = 1., 'CLEAR', None
    for t in tracks:
        for step in range(41):
            tm = step*horizon/40
            angle = yaw_rate*tm
            rx = speed*tm if abs(yaw_rate) < 1e-5 else speed/yaw_rate*math.sin(angle)
            ry = 0. if abs(yaw_rate) < 1e-5 else speed/yaw_rate*(1-math.cos(angle))
            tx, ty = t['x_m']+t['vx_mps']*tm, t['y_m']+t['vy_mps']*tm
            lx, ly = rotate(tx-rx, ty-ry, -angle)
            padding = cfg['target_radius_m']+cfg['margin_m']+t['age_s']*cfg['uncertainty_mps']
            if abs(ly) > cfg['half_width_m']+padding:
                continue
            gap = direction*lx-cfg['half_length_m']-padding
            if direction*lx < -cfg['half_length_m']-padding:
                continue
            # Approach is conservative even when firmware sign is unverified:
            # use |Doppler| in that case. Odom-derived target velocity already
            # moves the projected target above; do not add rover speed twice.
            approach = max(0., -t['relative_radial_mps']) if cfg['speed_sign_verified'] else abs(t['relative_radial_mps'])
            needed = braking + approach*(reaction+v/decel)
            candidate = max(0., min(1., gap/max(0.05, needed+cfg['slow_band_m'])))
            if gap <= needed and (tm == 0 or gap <= 0):
                candidate = 0.
            if candidate < scale:
                scale, reason, hazard = candidate, 'TARGET_IN_SWEPT_PATH', t['track_id']
    return {'scale': scale, 'reason': reason, 'track_id': hazard,
            'braking_distance_m': braking, 'prediction_s': horizon}


def guard_scale(payload, age, timeout=0.5):
    """Fail closed when the optional local mux gate is enabled."""
    try:
        scale = float(payload['scale'])
        if age < 0 or age > timeout or not payload.get('qualified') or not math.isfinite(scale):
            return 0.
        return max(0., min(1., scale))
    except (TypeError, KeyError, ValueError):
        return 0.
