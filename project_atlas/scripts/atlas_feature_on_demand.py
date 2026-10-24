#!/usr/bin/env python3
"""ATLAS on-demand AI features: start a non-essential AI feature service when it is needed, stop it after it has been
unused for a while (owner request 24 Oct 2026 15:00). Safety, motion, sensor, localization, camera and voice services
are never managed here.

Demand comes only from existing low-rate topics (no LiDAR/image subscriptions):
  autonomy      /atlas/control_policy manual_only == false, or /atlas/mission_status != READY, or either is stale/missing
                (fail-open: unknown means "features on")
  ai_object     /atlas/ai_enabled true within the last 60 s (Dashboard object mode with a viewer, or voice)
  follow        latest /atlas/follow_person/enabled == true
  tracking      latest /atlas/camera_tracking/enabled == true
  active_vision /atlas/active_vision/request within the last 120 s

Rules:
  * Only units in MANAGED (hard-coded) can be started or stopped; the YAML file can only tune timings/triggers of
    those units. Nothing is ever restarted, enabled, disabled or edited.
  * Boot grace (default 300 s): nothing is stopped until ATLAS has settled.
  * A feature is stopped only after its demand has been false for its idle_s AND it has been on for min_on_s.
  * While a mapping session is active (atlas-slam-fast.service), units that mission control pauses for mapping
    (camera tracker, follow-person) are never started by this manager.
  * When a follow/tracking/active-vision feature finishes starting, the owner's LATEST command for it is replayed once,
    only if it is still the latest and younger than replay_max_age_s.
  * `restore-all` (used by the systemd unit's ExecStopPost) starts every managed unit again = today's always-on state.

usage:  atlas_feature_on_demand.py run [--config config/atlas_feature_on_demand.yaml]
        atlas_feature_on_demand.py restore-all
"""
import argparse, json, os, subprocess, sys, time
from pathlib import Path

MANAGED = {   # unit -> default triggers / idle seconds / replay topic. HARD ALLOWLIST.
    'atlas-vision-lidar-fusion': {'triggers': ['autonomy'], 'idle_s': 300},
    'atlas-person-sensor-fusion': {'triggers': ['autonomy', 'follow'], 'idle_s': 300},
    'atlas-experience-store': {'triggers': ['autonomy'], 'idle_s': 300},
    'atlas-agent-team': {'triggers': ['autonomy'], 'idle_s': 300},
    'atlas-ai-annotator': {'triggers': ['autonomy', 'ai_object', 'follow', 'tracking'], 'idle_s': 300},
    'atlas-follow-person': {'triggers': ['follow'], 'idle_s': 120, 'replay': 'follow'},
    'atlas-camera-tracker': {'triggers': ['tracking'], 'idle_s': 120, 'replay': 'tracking'},
    'atlas-active-vision': {'triggers': ['active_vision'], 'idle_s': 120, 'replay': 'active_vision'},
}
MAPPING_PAUSED = {'atlas-camera-tracker', 'atlas-follow-person'}   # mission control owns these during mapping
TRIGGERS = ('autonomy', 'ai_object', 'follow', 'tracking', 'active_vision')
SYSTEMCTL = os.environ.get('ATLAS_SYSTEMCTL', 'systemctl')
DEFAULTS = {'boot_grace_s': 300, 'min_on_s': 60, 'state_check_s': 15, 'policy_stale_s': 5.0, 'mission_stale_s': 10.0,
            'ai_window_s': 60, 'active_vision_window_s': 120, 'replay_delay_s': 4.0, 'replay_max_age_s': 60.0}


def log(event, **kw):
    print(json.dumps(dict(t=round(time.time(), 3), event=event, **kw), default=str), flush=True)


def load_config(path):
    cfg = dict(DEFAULTS); features = {u: dict(v) for u, v in MANAGED.items()}
    if path and Path(path).exists():
        import yaml
        raw = yaml.safe_load(Path(path).read_text()) or {}
        for k, v in (raw.get('timing') or {}).items():
            if k in DEFAULTS:
                cfg[k] = float(v)
        for unit, v in (raw.get('features') or {}).items():
            if unit not in MANAGED:
                raise SystemExit('config names an unmanaged unit: %s (allowlist is fixed in code)' % unit)
            if 'idle_s' in v:
                features[unit]['idle_s'] = max(30.0, float(v['idle_s']))
            if 'triggers' in v:
                bad = set(v['triggers']) - set(TRIGGERS)
                if bad or not v['triggers']:
                    raise SystemExit('invalid triggers for %s: %s' % (unit, v['triggers']))
                features[unit]['triggers'] = list(v['triggers'])
            if v.get('always_on'):
                features[unit]['always_on'] = True
    return cfg, features


class Demand:
    """Pure demand bookkeeping (unit-testable without ROS)."""
    def __init__(self, cfg, clock=time.monotonic):
        self.cfg, self.clock = cfg, clock
        self.policy = None; self.policy_t = None; self.mission = None; self.mission_t = None
        self.ai_true_t = None; self.follow = None; self.tracking = None; self.av_t = None
        self.last_cmd = {}   # replay key -> (monotonic time, payload)

    def on_policy(self, text):
        try:
            p = json.loads(text) if isinstance(text, str) else text
            self.policy = p if isinstance(p, dict) else None
        except ValueError:
            self.policy = None
        self.policy_t = self.clock()

    def on_mission(self, text): self.mission = text.strip(); self.mission_t = self.clock()
    def on_ai(self, v):
        if v: self.ai_true_t = self.clock()
    def on_follow(self, v): self.follow = bool(v); self.last_cmd['follow'] = (self.clock(), bool(v))
    def on_tracking(self, v): self.tracking = bool(v); self.last_cmd['tracking'] = (self.clock(), bool(v))
    def on_active_vision(self, text): self.av_t = self.clock(); self.last_cmd['active_vision'] = (self.clock(), text)

    def active(self):
        now = self.clock(); c = self.cfg
        policy_ok = self.policy is not None and self.policy_t is not None and now - self.policy_t <= c['policy_stale_s']
        mission_ok = self.mission is not None and self.mission_t is not None and now - self.mission_t <= c['mission_stale_s']
        autonomy = (not policy_ok) or self.policy.get('manual_only') is not True or (not mission_ok) or self.mission != 'READY'
        return {'autonomy': autonomy,
                'ai_object': self.ai_true_t is not None and now - self.ai_true_t <= c['ai_window_s'],
                'follow': self.follow is True,
                'tracking': self.tracking is True,
                'active_vision': self.av_t is not None and now - self.av_t <= c['active_vision_window_s']}

    def replay_payload(self, key):
        """Latest command for this feature if it is still recent; None otherwise (never invent a command)."""
        item = self.last_cmd.get(key)
        if not item or self.clock() - item[0] > self.cfg['replay_max_age_s']:
            return None
        return item[1]


class Planner:
    """Decides start/stop per unit from demand, idle timers, boot grace and min-on time (pure, unit-testable)."""
    def __init__(self, cfg, features, clock=time.monotonic):
        self.cfg, self.features, self.clock = cfg, features, clock
        self.started_at = clock(); self.on_since = {u: clock() for u in features}; self.unused_since = {}

    def decide(self, active, state, mapping_active):
        now = self.clock(); actions = []
        for u, f in self.features.items():
            need = f.get('always_on') or any(active.get(t) for t in f['triggers'])
            running = state.get(u) == 'active'
            if need:
                self.unused_since.pop(u, None)
                if not running and not (u in MAPPING_PAUSED and mapping_active()):
                    actions.append(('start', u))
            else:
                self.unused_since.setdefault(u, now)
                if running and now - self.started_at >= self.cfg['boot_grace_s'] \
                        and now - self.unused_since[u] >= f['idle_s'] and now - self.on_since.get(u, 0) >= self.cfg['min_on_s']:
                    actions.append(('stop', u))
        return actions

    def note_started(self, u): self.on_since[u] = self.clock()


def systemctl(*args, timeout=60):
    return subprocess.run([SYSTEMCTL, '--user', *args], capture_output=True, text=True, timeout=timeout)


def unit_state(u):
    return systemctl('is-active', u + '.service', timeout=10).stdout.strip() or 'unknown'


def restore_all():
    out = {}
    for u in MANAGED:
        r = systemctl('start', u + '.service'); out[u] = r.returncode
    log('restore_all', results=out)


def run(config):
    import rclpy
    from std_msgs.msg import Bool, String
    cfg, features = load_config(config)
    rclpy.init(); node = rclpy.create_node('atlas_feature_on_demand')
    dem = Demand(cfg); plan = Planner(cfg, features)
    node.create_subscription(String, '/atlas/control_policy', lambda m: dem.on_policy(m.data), 10)
    node.create_subscription(String, '/atlas/mission_status', lambda m: dem.on_mission(m.data), 10)
    node.create_subscription(Bool, '/atlas/ai_enabled', lambda m: dem.on_ai(m.data), 10)
    node.create_subscription(Bool, '/atlas/follow_person/enabled', lambda m: dem.on_follow(m.data), 10)
    node.create_subscription(Bool, '/atlas/camera_tracking/enabled', lambda m: dem.on_tracking(m.data), 10)
    node.create_subscription(String, '/atlas/active_vision/request', lambda m: dem.on_active_vision(m.data), 10)
    pubs = {'follow': node.create_publisher(Bool, '/atlas/follow_person/enabled', 10),
            'tracking': node.create_publisher(Bool, '/atlas/camera_tracking/enabled', 10),
            'active_vision': node.create_publisher(String, '/atlas/active_vision/request', 10)}
    state = {u: unit_state(u) for u in features}; last_check = time.monotonic(); pending_replay = {}
    log('start', features={u: f for u, f in features.items()}, timing=cfg, state=state)

    def tick():
        nonlocal last_check, state
        now = time.monotonic()
        if now - last_check >= cfg['state_check_s']:
            state = {u: unit_state(u) for u in features}; last_check = now
        active = dem.active()
        mapping = lambda: unit_state('atlas-slam-fast') == 'active'     # checked only before starting a mapping-paused unit
        for action, u in plan.decide(active, state, mapping):
            r = systemctl(action, u + '.service')
            state[u] = unit_state(u)
            log(action, unit=u, rc=r.returncode, state=state[u], demand={k: v for k, v in active.items() if v})
            if action == 'start' and state[u] == 'active':
                plan.note_started(u)
                if features[u].get('replay'):
                    pending_replay[u] = now + cfg['replay_delay_s']
        for u, due in list(pending_replay.items()):
            if now >= due:
                key = features[u]['replay']; payload = dem.replay_payload(key); pending_replay.pop(u)
                if payload is None or (key in ('follow', 'tracking') and payload is not True):
                    log('replay_skipped', unit=u, reason='no recent enabling command'); continue
                msg = Bool(data=True) if key in ('follow', 'tracking') else String(data=payload)
                pubs[key].publish(msg); log('replay', unit=u, topic=key)

    node.create_timer(1.0, tick)
    try:
        rclpy.spin(node)
    finally:
        node.destroy_node(); rclpy.shutdown()


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('cmd', choices=('run', 'restore-all'))
    ap.add_argument('--config', default=str(Path(__file__).resolve().parents[1] / 'config/atlas_feature_on_demand.yaml'))
    a = ap.parse_args()
    restore_all() if a.cmd == 'restore-all' else run(a.config)


if __name__ == '__main__':
    main()
