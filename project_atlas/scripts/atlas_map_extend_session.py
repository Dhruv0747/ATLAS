"""Extend-map sessions (2026-11-26; owner: "don't disturb the saved map; add the new places"). Pure helpers used by
atlas_mission_control.py. Design: docs/design/guided_mapping_assistant.md section 10.

An extend session is a normal owner-driven SLAM session with three differences, all on the safe side:
  * it may start only from a fresh, unique LiDAR-verified position on the saved map (the localization monitor's
    VERIFIED state), and records T = P_map * inverse(P_odom) at that moment: SLAM starts with map == odom, so T maps
    the new piece's frame into the saved map's frame (the merge refines it);
  * it never overwrites the saved home pose or the saved map's localization seed;
  * at stop it saves the piece and writes a request for the extend job, and NEVER promotes anything. The saved map
    changes only through the preview, the checks and the owner's explicit OK.
"""
import json
import math
import os
from pathlib import Path
import time
import uuid

EXTEND_MODE = 'extend_teaching'
CHECK_WRITE_MAX_AGE_S = 15.0        # the localization monitor writes about once a second
CHECK_MAX_AGE_S = 60.0              # the LiDAR comparison itself must be recent


def is_extend(session):
    return bool(session) and session.get('mode') == EXTEND_MODE


def extend_start_refusal(check, now):
    """None when an extend session may start, else an English reason (fail closed)."""
    if not isinstance(check, dict):
        return 'no LiDAR localization check available: start the localization monitor and park at a known spot'
    written, checked = check.get('written_unix'), check.get('checked_unix')
    if not isinstance(written, (int, float)) or now - written > CHECK_WRITE_MAX_AGE_S:
        return 'the LiDAR localization check is not running (no fresh result)'
    if check.get('state') != 'VERIFIED':
        return (f"extend mapping needs a LiDAR-verified start (now {check.get('state')}): park where the Mapping page "
                f"says LOCALIZATION VERIFIED BY LIDAR and try again")
    if not isinstance(checked, (int, float)) or now - checked > CHECK_MAX_AGE_S:
        return f'the last LiDAR verification is older than {CHECK_MAX_AGE_S:.0f} s: stay parked until it re-checks'
    return None


def _yaw(p):
    return math.atan2(2.0 * (p['qw'] * p['qz'] + p['qx'] * p['qy']), 1.0 - 2.0 * (p['qy'] ** 2 + p['qz'] ** 2))


def compose_init(map_pose, odom_pose):
    """T = P_map * inverse(P_odom) as (tx, ty, yaw). map_pose must be in frame 'map', odom_pose in 'odom'."""
    if map_pose.get('frame_id') != 'map' or odom_pose.get('frame_id') != 'odom':
        raise ValueError('extend start needs a map-frame pose and an odom-frame pose')
    am, ao = _yaw(map_pose), _yaw(odom_pose)
    th = math.atan2(math.sin(am - ao), math.cos(am - ao))
    c, s = math.cos(th), math.sin(th)
    ox, oy = float(odom_pose['x']), float(odom_pose['y'])
    return (float(map_pose['x']) - (c * ox - s * oy), float(map_pose['y']) - (s * ox + c * oy), th)


def write_request(state_dir, session, candidate_yaml, end_pose_slam):
    """Atomic request file for the extend job: <state_dir>/<session id>.request.json."""
    state_dir = Path(state_dir)
    state_dir.mkdir(parents=True, exist_ok=True)
    ext = session.get('extend') or {}
    req = {'schema': 1, 'session_id': session['id'], 'state': 'pending', 'created_unix': time.time(),
           'candidate_yaml': str(candidate_yaml), 'base_map_id': ext.get('base_map_id'), 'init': ext.get('init'),
           'start_map_pose': ext.get('start_map_pose'), 'end_pose_slam': end_pose_slam}
    path = state_dir / f"{session['id']}.request.json"
    tmp = path.with_name(f'.{path.name}.{uuid.uuid4().hex}.tmp')
    tmp.write_text(json.dumps(req, indent=2), encoding='utf-8')
    os.replace(tmp, path)
    return path
