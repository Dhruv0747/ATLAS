#!/usr/bin/env python3
"""Bounded, non-actuating AMCL shadow capture on a stationary ATLAS.

Requires the separately built Nav2 1.1.20 trace binary. The production AMCL
process, localization parameters, TF broadcaster and motor stack are untouched.
"""

import argparse
import hashlib
import json
import os
from pathlib import Path
import signal
import subprocess
import time

import rclpy
from geometry_msgs.msg import PoseWithCovarianceStamped
from lifecycle_msgs.msg import Transition
from lifecycle_msgs.srv import ChangeState, GetState
from rcl_interfaces.srv import GetParameters
from rclpy.node import Node
from rclpy.qos import DurabilityPolicy, QoSProfile, ReliabilityPolicy
from rclpy.time import Time
from std_srvs.srv import Empty
import yaml


SHADOW = "/atlas_shadow/amcl"
TOPICS = (
    "/scan", "/map", "/tf", "/tf_static", "/odom", "/yahboom/odom",
    "/imu/data", "/im10a/imu/bias_corrected_candidate", "/amcl_pose",
    "/particle_cloud", "/atlas_shadow/amcl_pose",
    "/atlas_shadow/particle_cloud",
    "/atlas_shadow/atlas_debug/amcl/pre_resample_particle_cloud", "/rosout",
)


def sha256(path):
    digest = hashlib.sha256()
    with open(path, "rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def stop_process(process):
    if process is None or process.poll() is not None:
        return
    process.send_signal(signal.SIGINT)
    try:
        process.wait(timeout=12)
    except subprocess.TimeoutExpired:
        process.terminate()
        process.wait(timeout=5)


class CaptureNode(Node):
    def __init__(self):
        super().__init__("atlas_amcl_shadow_capture")
        self.production_pose = None
        self.shadow_poses = 0
        pose_qos = QoSProfile(
            depth=1, durability=DurabilityPolicy.TRANSIENT_LOCAL,
            reliability=ReliabilityPolicy.RELIABLE)
        self.create_subscription(
            PoseWithCovarianceStamped, "/amcl_pose", self.on_production_pose,
            pose_qos)
        self.create_subscription(
            PoseWithCovarianceStamped, "/atlas_shadow/amcl_pose",
            self.on_shadow_pose, pose_qos)
        self.configure = self.create_client(ChangeState, SHADOW + "/change_state")
        self.state = self.create_client(GetState, SHADOW + "/get_state")
        self.parameters = self.create_client(GetParameters, SHADOW + "/get_parameters")
        self.nomotion = self.create_client(Empty, "/atlas_shadow/request_nomotion_update")
        self.seed = self.create_publisher(
            PoseWithCovarianceStamped, "/atlas_shadow/initialpose", 10)

    def on_production_pose(self, msg):
        self.production_pose = msg

    def on_shadow_pose(self, _msg):
        self.shadow_poses += 1


def until(node, predicate, seconds):
    deadline = time.monotonic() + seconds
    while time.monotonic() < deadline:
        rclpy.spin_once(node, timeout_sec=0.2)
        if predicate():
            return True
    return False


def transition(node, transition_id):
    if not node.configure.wait_for_service(timeout_sec=10):
        raise RuntimeError("shadow lifecycle service unavailable")
    request = ChangeState.Request()
    request.transition.id = transition_id
    future = node.configure.call_async(request)
    expected = "inactive" if transition_id == Transition.TRANSITION_CONFIGURE else "active"
    if until(node, lambda: future.done(), 15):
        if not future.result().success:
            raise RuntimeError(f"shadow lifecycle transition {transition_id} rejected")
        return
    # On a busy Jetson the lifecycle server may perform the transition but
    # miss the RPC reply deadline. Verify actual shadow state before failing.
    if not node.state.wait_for_service(timeout_sec=5):
        raise RuntimeError("shadow state service unavailable")
    state_future = node.state.call_async(GetState.Request())
    if not until(node, lambda: state_future.done(), 10):
        raise RuntimeError(f"shadow lifecycle transition {transition_id} unverified")
    if state_future.result().current_state.label != expected:
        raise RuntimeError(f"shadow expected {expected}, got "
                           f"{state_future.result().current_state.label}")


def verify_shadow_parameters(node):
    if not node.parameters.wait_for_service(timeout_sec=5):
        raise RuntimeError("shadow parameter service unavailable")
    request = GetParameters.Request()
    request.names = ["tf_broadcast", "map_topic", "scan_topic", "max_particles"]
    future = node.parameters.call_async(request)
    if not until(node, lambda: future.done(), 10):
        raise RuntimeError("shadow parameter query timed out")
    values = future.result().values
    if not (values[0].bool_value is False and values[1].string_value == "/map"
            and values[2].string_value == "/scan" and values[3].integer_value == 2000):
        raise RuntimeError("shadow parameter mismatch; aborting before activation")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--binary", required=True, type=Path)
    parser.add_argument("--params", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--seconds", type=int, default=25)
    args = parser.parse_args()
    if not 10 <= args.seconds <= 60:
        parser.error("capture duration must be 10–60 seconds")
    if not args.binary.is_file() or not args.params.is_file():
        parser.error("shadow binary or parameter file missing")
    params = yaml.safe_load(args.params.read_text(encoding="utf-8"))
    values = params["/**"]["ros__parameters"]
    if values["tf_broadcast"] is not False or values["map_topic"] != "/map":
        parser.error("shadow configuration must disable TF and use the live map")
    args.output.mkdir(parents=True, exist_ok=False)
    env = os.environ.copy()
    env["OMP_NUM_THREADS"] = "1"
    shadow = recorder = None
    rclpy.init()
    node = CaptureNode()
    manifest = {
        "status": "started", "duration_s": args.seconds,
        "shadow_binary_sha256": sha256(args.binary),
        "shadow_params_sha256": sha256(args.params),
        "topics": TOPICS, "production_changed": False,
        "motor_commands_sent": False,
    }
    try:
        if not until(node, lambda: node.production_pose is not None, 10):
            raise RuntimeError("fresh production AMCL pose unavailable; no shadow started")
        age_s = (node.get_clock().now().nanoseconds -
                 Time.from_msg(node.production_pose.header.stamp).nanoseconds) / 1e9
        if not 0 <= age_s <= 3:
            raise RuntimeError(f"production AMCL seed is stale ({age_s:.1f} s)")
        pose = node.production_pose.pose.pose
        manifest["seed_from_production_pose"] = {
            "x": pose.position.x, "y": pose.position.y,
            "orientation_z": pose.orientation.z, "orientation_w": pose.orientation.w,
        }
        shadow_log = open(args.output / "shadow.log", "w", encoding="utf-8")
        try:
            shadow = subprocess.Popen(
                [str(args.binary), "--ros-args", "-r", "__ns:=/atlas_shadow",
                 "-r", "tf:=/tf", "-r", "tf_static:=/tf_static",
                 "--params-file", str(args.params)],
                stdout=shadow_log, stderr=subprocess.STDOUT, env=env,
                start_new_session=True)
            transition(node, Transition.TRANSITION_CONFIGURE)
            verify_shadow_parameters(node)
            transition(node, Transition.TRANSITION_ACTIVATE)
            recorder_log = open(args.output / "recorder.log", "w", encoding="utf-8")
            try:
                recorder = subprocess.Popen(
                    ["ros2", "bag", "record", "--storage", "sqlite3", "-o",
                     str(args.output / "bag"), *TOPICS],
                    stdout=recorder_log, stderr=subprocess.STDOUT, env=env,
                    start_new_session=True)
                time.sleep(2)
                seed = PoseWithCovarianceStamped()
                seed.header.frame_id = "map"
                seed.header.stamp = node.get_clock().now().to_msg()
                seed.pose = node.production_pose.pose
                node.seed.publish(seed)
                if not until(node, lambda: node.shadow_poses > 0, 8):
                    raise RuntimeError("shadow did not accept initial pose")
                if not node.nomotion.wait_for_service(timeout_sec=5):
                    raise RuntimeError("shadow no-motion service unavailable")
                deadline = time.monotonic() + args.seconds
                next_request = time.monotonic()
                calls = 0
                while time.monotonic() < deadline:
                    now = time.monotonic()
                    if now >= next_request:
                        node.nomotion.call_async(Empty.Request())
                        calls += 1
                        next_request += 1.0
                    rclpy.spin_once(node, timeout_sec=min(0.2, max(0.0, next_request - now)))
                    if shadow.poll() is not None or recorder.poll() is not None:
                        raise RuntimeError("shadow or recorder exited early")
                manifest.update(status="complete", nomotion_calls=calls,
                                shadow_pose_messages=node.shadow_poses)
            finally:
                stop_process(recorder)
                recorder_log.close()
        finally:
            stop_process(shadow)
            shadow_log.close()
    except Exception as exc:
        manifest.update(status="failed", error=str(exc))
        raise
    finally:
        (args.output / "manifest.json").write_text(
            json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
        node.destroy_node()
        if rclpy.ok():
            rclpy.shutdown()
    print(json.dumps(manifest, indent=2))


if __name__ == "__main__":
    main()
