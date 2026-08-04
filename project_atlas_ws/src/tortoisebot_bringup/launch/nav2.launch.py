#!/usr/bin/env python3
"""
Nav2 navigation launch file for TortoiseBot mecanum robot.
Starts: map_server, amcl, nav2_lifecycle_manager, planner, controller, bt_navigator, behaviors.
Requires: a saved map at ~/my_map.yaml (run SLAM first and save the map)
Usage: ros2 launch tortoisebot_bringup nav2.launch.py
       ros2 launch tortoisebot_bringup nav2.launch.py map:=/home/jetson/project_atlas/maps/my_map.yaml
"""
import os
from launch import LaunchDescription
from launch.actions import DeclareLaunchArgument, IncludeLaunchDescription
from launch.substitutions import LaunchConfiguration
from launch_ros.actions import Node
from ament_index_python.packages import get_package_share_directory


def generate_launch_description():
    pkg = get_package_share_directory("tortoisebot_bringup")
    nav2_params_file = os.path.join(pkg, "config", "nav2_params.yaml")

    map_file = LaunchConfiguration("map")
    use_sim_time = LaunchConfiguration("use_sim_time", default="false")

    return LaunchDescription([
        DeclareLaunchArgument(
            "map",
            default_value="/home/jetson/project_atlas/maps/my_map.yaml",
            description="Full path to map yaml file"
        ),
        DeclareLaunchArgument(
            "use_sim_time",
            default_value="false",
            description="Use simulation time"
        ),

        # Map server - loads the saved map
        Node(
            package="nav2_map_server",
            executable="map_server",
            name="map_server",
            output="screen",
            parameters=[
                nav2_params_file,
                {"yaml_filename": map_file,
                 "use_sim_time": use_sim_time}
            ]
        ),

        # AMCL - localizes robot on the map using lidar
        Node(
            package="nav2_amcl",
            executable="amcl",
            name="amcl",
            output="screen",
            parameters=[
                nav2_params_file,
                {"use_sim_time": use_sim_time}
            ]
        ),

        # Planner server - computes global paths
        Node(
            package="nav2_planner",
            executable="planner_server",
            name="planner_server",
            output="screen",
            parameters=[
                nav2_params_file,
                {"use_sim_time": use_sim_time}
            ]
        ),

        # Controller server - follows paths with local obstacle avoidance
        Node(
            package="nav2_controller",
            executable="controller_server",
            name="controller_server",
            output="screen",
            parameters=[
                nav2_params_file,
                {"use_sim_time": use_sim_time}
            ],
            remappings=[("cmd_vel", "cmd_vel")]
        ),

        # Smoother server
        Node(
            package="nav2_smoother",
            executable="smoother_server",
            name="smoother_server",
            output="screen",
            parameters=[
                nav2_params_file,
                {"use_sim_time": use_sim_time}
            ]
        ),

        # Behavior server - spin, backup, wait behaviors
        Node(
            package="nav2_behaviors",
            executable="behavior_server",
            name="behavior_server",
            output="screen",
            parameters=[
                nav2_params_file,
                {"use_sim_time": use_sim_time}
            ]
        ),

        # BT Navigator - orchestrates the navigation behavior tree
        Node(
            package="nav2_bt_navigator",
            executable="bt_navigator",
            name="bt_navigator",
            output="screen",
            parameters=[
                nav2_params_file,
                {"use_sim_time": use_sim_time}
            ]
        ),

        # Waypoint follower
        Node(
            package="nav2_waypoint_follower",
            executable="waypoint_follower",
            name="waypoint_follower",
            output="screen",
            parameters=[
                nav2_params_file,
                {"use_sim_time": use_sim_time}
            ]
        ),

        # Velocity smoother
        Node(
            package="nav2_velocity_smoother",
            executable="velocity_smoother",
            name="velocity_smoother",
            output="screen",
            parameters=[
                nav2_params_file,
                {"use_sim_time": use_sim_time}
            ],
            remappings=[
                ("cmd_vel", "cmd_vel_nav"),
                ("cmd_vel_smoothed", "cmd_vel")
            ]
        ),

        # Lifecycle manager - manages all Nav2 node lifecycles
        Node(
            package="nav2_lifecycle_manager",
            executable="lifecycle_manager",
            name="lifecycle_manager_navigation",
            output="screen",
            parameters=[{
                "use_sim_time": use_sim_time,
                "autostart": True,
                "node_names": [
                    "map_server",
                    "amcl",
                    "planner_server",
                    "controller_server",
                    "smoother_server",
                    "behavior_server",
                    "bt_navigator",
                    "waypoint_follower",
                    "velocity_smoother",
                ]
            }]
        ),
    ])
