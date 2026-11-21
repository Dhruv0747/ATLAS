"""Single bounded camera-free discovery discriminator; no control interfaces.

Only explicit parent GO after import warmup permits this new test ROS node.
No explicit user-topic subscriptions/publishers, parameter writes, service calls
or motion requests. ROS itself may create its normal discovery/parameter plumbing.
"""
import sys
import time
import rclpy


def main():
    print('STAGE30_IMPORT_READY',flush=True)
    if sys.stdin.readline().strip()!='GO':raise SystemExit('parent approval absent')
    begin=time.monotonic();rclpy.init()
    node=None
    try:
        node=rclpy.create_node('atlas_stage30_camera_free_discovery_probe',
                              enable_rosout=False,start_parameter_services=False)
        print('STAGE30_GRAPH_JOINED '+str(time.monotonic()-begin),flush=True)
        until=time.monotonic()+6
        while time.monotonic()<until:rclpy.spin_once(node,timeout_sec=.1)
    finally:
        if node:node.destroy_node()
        if rclpy.ok():rclpy.shutdown()


if __name__=='__main__':main()
