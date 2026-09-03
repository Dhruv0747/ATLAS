import os
from launch import LaunchDescription
from launch.actions import ExecuteProcess, TimerAction
from launch_ros.actions import Node
from launch.substitutions import Command
from launch_ros.parameter_descriptions import ParameterValue
from ament_index_python.packages import get_package_share_directory


def generate_launch_description():
    return LaunchDescription([
        ExecuteProcess(cmd=["/home/jetson/project_atlas/scripts/camera_start.sh"], output="screen", name="camera"),
        ExecuteProcess(cmd=["/home/jetson/project_atlas/scripts/rplidar_start.sh"], output="screen", name="rplidar"),
        Node(package="tf2_ros", executable="static_transform_publisher", name="laser_tf",
            arguments=["0","0","0.18","3.14159265","0","0","base_footprint","laser_frame"]),
#         Node(package="tf2_ros", executable="static_transform_publisher", name="odom_tf",
#             arguments=["0","0","0","0","0","0","odom","base_footprint"]),
        Node(package="foxglove_bridge", executable="foxglove_bridge", name="foxglove_bridge",
            output="screen", parameters=[{"port": 8765, "capabilities": ["clientPublish", "connectionGraph", "assets", "parameters", "parametersSubscribe", "services"]}], respawn=True, respawn_delay=5.0),
#         Node(package="tortoisebot_motor_py", executable="motor_node", name="motor_node",
#             output="screen", respawn=True, respawn_delay=5.0),
        # The Yahboom base service owns the canonical /imu/* topics. Do not
        # launch a second IMU publisher from this aggregate launch file.
        TimerAction(period=25.0, actions=[
            Node(package="slam_toolbox", executable="async_slam_toolbox_node", name="slam_toolbox",
                output="screen", parameters=[{
                    "use_sim_time": False, "odom_frame": "odom", "map_frame": "map",
                    "base_frame": "base_footprint", "scan_topic": "/scan", "mode": "mapping",
                    "max_laser_range": 8.0, "minimum_travel_distance": 0.5,
                    "minimum_travel_heading": 0.5,
                }])
        ]),
        TimerAction(period=50.0, actions=[
            ExecuteProcess(cmd=["/home/jetson/project_atlas/scripts/slam_activate.sh"], output="screen")
        ]),
        Node(
            package="robot_state_publisher",
            executable="robot_state_publisher",
            name="robot_state_publisher",
            parameters=[{
                "robot_description": ParameterValue(
                    Command(["xacro ", os.path.join(
                        get_package_share_directory("tortoisebot_bringup"),
                        "urdf", "tortoisebot.urdf.xacro"
                    )]),
                    value_type=str
                )
            }],
            output="screen"
        ),
            TimerAction(period=70.0, actions=[
            ExecuteProcess(
                cmd=['/home/jetson/project_atlas/scripts/nav2_launch.sh'],
                output='screen',
                respawn=True,
                respawn_delay=15.0
            )
        ]),
    ])

