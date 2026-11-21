"""Isolated optional MediaPipe worker (gesture / body pose / face detection).

Runs under the dedicated vision-mediapipe venv, never the system/ROS Python. Same IPC and safety contract as
atlas_vision_feature_worker.py: input is existing viewer RGB passed by the parent over stdin (no camera, ROS or
servo access), JSON-only stdout, parent-death SIGKILL, bounded startup and per-frame deadlines, guard lease and
1 s input age. Face mode returns boxes only: no identity, embeddings, crops or images are produced or stored.
"""
import base64
import ctypes
import hashlib
import json
import math
import os
import resource
import select
import signal
import sys
import time
from pathlib import Path

_IPC = os.fdopen(os.dup(1), 'w', buffering=1)
os.dup2(2, 1)  # MediaPipe/TFLite native logging must never reach the JSON channel


def emit(value):
    _IPC.write(json.dumps(value, allow_nan=False)+'\n'); _IPC.flush()


def _box(points, w, h):
    xs = [min(max(p[0], 0.0), 1.0)*w for p in points]; ys = [min(max(p[1], 0.0), 1.0)*h for p in points]
    return [round(min(xs), 1), round(min(ys), 1), round(max(xs), 1), round(max(ys), 1)]


def build(feature, model):
    import mediapipe as mp
    from mediapipe.tasks.python import BaseOptions, vision
    base = BaseOptions(model_asset_path=model)
    if feature == 'gesture':
        task = vision.GestureRecognizer.create_from_options(vision.GestureRecognizerOptions(
            base_options=base, running_mode=vision.RunningMode.IMAGE, num_hands=2))

        def run(image, w, h):
            r = task.recognize(image); rows = []
            for i, hand in enumerate(r.hand_landmarks):
                g = r.gestures[i][0] if i < len(r.gestures) and r.gestures[i] else None
                side = r.handedness[i][0].category_name if i < len(r.handedness) and r.handedness[i] else ''
                label = g.category_name if g and g.category_name not in ('', 'None') else 'hand'
                rows.append(dict(box=_box([(p.x, p.y) for p in hand], w, h), label=label, hand=side,
                                 confidence=round(float(g.score if g else 0.0), 3), distance_m=None))
            return rows
    elif feature == 'body':
        task = vision.PoseLandmarker.create_from_options(vision.PoseLandmarkerOptions(
            base_options=base, running_mode=vision.RunningMode.IMAGE, num_poses=2))

        def run(image, w, h):
            rows = []
            for pose in task.detect(image).pose_landmarks:
                vis = [float(p.visibility) for p in pose]
                seen = [p for p in pose if p.visibility >= .5] or list(pose)
                rows.append(dict(box=_box([(p.x, p.y) for p in seen], w, h), label='person (33-point pose)',
                                 confidence=round(sum(vis)/len(vis), 3), distance_m=None,
                                 keypoints=[[round(p.x*w, 1), round(p.y*h, 1), round(float(p.visibility), 2)] for p in pose]))
            return rows
    elif feature == 'face':
        task = vision.FaceDetector.create_from_options(vision.FaceDetectorOptions(
            base_options=base, running_mode=vision.RunningMode.IMAGE, min_detection_confidence=.5))

        def run(image, w, h):
            rows = []
            for d in task.detect(image).detections:
                b = d.bounding_box
                rows.append(dict(box=[float(b.origin_x), float(b.origin_y), float(b.origin_x+b.width), float(b.origin_y+b.height)],
                                 label='face (detection only, no identity)',
                                 confidence=round(float(d.categories[0].score if d.categories else 0.0), 3), distance_m=None))
            return rows
    else:
        raise ValueError('unsupported feature')
    return mp, task, run


def main():
    parent = os.getppid()
    ctypes.CDLL(None).prctl(1, signal.SIGKILL)  # Linux parent-death cleanup
    if os.getppid() != parent: raise RuntimeError('parent changed')
    signal.alarm(8)  # startup deadline including model load (TFLite on CPU)
    resource.setrlimit(resource.RLIMIT_CORE, (0, 0))
    feature, model, expected = sys.argv[1:]
    if feature not in ('gesture', 'body', 'face'): raise ValueError('unsupported feature')
    if hashlib.sha256(Path(model).read_bytes()).hexdigest() != expected: raise ValueError('model hash mismatch')
    import numpy as np
    mp, task, run = build(feature, model)
    deadline = time.monotonic()+60
    emit({'ready': True})
    signal.alarm(0)
    try:
        while time.monotonic() < deadline:
            if not select.select([sys.stdin], [], [], 2)[0]: break
            signal.alarm(2)  # bounded IPC/inference even if parent guard stalls
            line = sys.stdin.buffer.readline(9_000_000)
            if not line: break
            if not line.endswith(b'\n'): raise ValueError('oversized frame')
            m = json.loads(line); w, h = m['width'], m['height']
            lease = m['guard_expires_mono']-time.monotonic()
            if not math.isfinite(lease) or not 0 < lease <= 2: raise ValueError('expired/invalid safety lease')
            signal.setitimer(signal.ITIMER_REAL, lease)
            if type(w) != int or type(h) != int or not 0 < w <= 1920 or not 0 < h <= 1080: raise ValueError('dimensions')
            if not 0 <= time.time_ns()-m['stamp_ns'] <= 1_000_000_000: raise ValueError('stale input')
            raw = base64.b64decode(m['rgb'], validate=True)
            if len(raw) != w*h*3: raise ValueError('payload size')
            started = time.process_time(); wall = time.monotonic()
            rgb = np.ascontiguousarray(np.frombuffer(raw, np.uint8).reshape(h, w, 3))
            rows = run(mp.Image(image_format=mp.ImageFormat.SRGB, data=rgb), w, h)
            result = dict(stamp_ns=m['stamp_ns'], stamp_ns_exact=str(m['stamp_ns']), width=w, height=h, detections=rows,
                          inference_s=time.monotonic()-wall, cpu_s=time.process_time()-started,
                          peak_rss_kib=resource.getrusage(resource.RUSAGE_SELF).ru_maxrss)
            emit(result)
            signal.setitimer(signal.ITIMER_REAL, 0)  # frame answered: do not let its bound fire while idle
    finally:
        task.close()


if __name__ == '__main__':
    try: main()
    except Exception as e:
        emit({'error': str(e)[:500]})
        sys.exit(1)
