#!/usr/bin/env python3
"""Saved-map localization and safe Nav2 bringup for Project ATLAS."""

from launch import LaunchDescription
from launch.actions import DeclareLaunchArgument, ExecuteProcess, TimerAction
from launch.substitutions import LaunchConfiguration
from launch_ros.actions import Node


PARAMS_FILE = (
    "/home/jetson/project_atlas_ws/src/"
    "tortoisebot_bringup/config/nav2_params.yaml"
)


def generate_launch_description():
    map_file = LaunchConfiguration("map")
    localization_managed = ["map_server", "amcl"]
    navigation_managed = [
        "controller_server",
        "planner_server",
        "behavior_server",
        "bt_navigator",
        "waypoint_follower",
    ]

    common = [PARAMS_FILE, {"use_sim_time": False}]
    map_server = Node(
        package="nav2_map_server",
        executable="map_server",
        name="map_server",
        output="screen",
        parameters=[PARAMS_FILE, {
            "yaml_filename": map_file,
            "use_sim_time": False,
        }],
    )
    amcl = Node(
        package="nav2_amcl",
        executable="amcl",
        name="amcl",
        output="screen",
        parameters=common,
    )
    localization_manager = Node(
        package="nav2_lifecycle_manager",
        executable="lifecycle_manager",
        name="lifecycle_manager_localization",
        output="screen",
        parameters=[{
            "use_sim_time": False,
            "autostart": True,
            "node_names": localization_managed,
            "bond_timeout": 4.0,
            "attempt_respawn_reconnection": True,
        }],
    )
    # 2026-11-16 owner-confirmed virtual obstacles (sofa / glass table / cabinet the LiDAR cannot see): republishes
    # /map as /map_nav with config/virtual_obstacles.json polygons occupied. Nav2 static layers read /map_nav;
    # AMCL keeps the untouched /map.
    virtual_obstacles = ExecuteProcess(
        cmd=["python3", "/home/jetson/project_atlas/scripts/atlas_virtual_obstacles.py"],
        name="atlas_virtual_obstacles",
        output="screen",
    )
    navigation_nodes = [
        Node(
            package="nav2_controller",
            executable="controller_server",
            name="controller_server",
            output="screen",
            parameters=common,
            remappings=[("cmd_vel", "cmd_vel_nav")],
        ),
        Node(
            package="nav2_planner",
            executable="planner_server",
            name="planner_server",
            output="screen",
            parameters=common,
        ),
        Node(
            package="nav2_behaviors",
            executable="behavior_server",
            name="behavior_server",
            output="screen",
            parameters=common,
            remappings=[("cmd_vel", "cmd_vel_nav")],
        ),
        Node(
            package="nav2_bt_navigator",
            executable="bt_navigator",
            name="bt_navigator",
            output="screen",
            parameters=common,
        ),
        Node(
            package="nav2_waypoint_follower",
            executable="waypoint_follower",
            name="waypoint_follower",
            output="screen",
            parameters=common,
        ),
        Node(
            package="nav2_lifecycle_manager",
            executable="lifecycle_manager",
            name="lifecycle_manager_navigation",
            output="screen",
            parameters=[{
                "use_sim_time": False,
                "autostart": True,
                "node_names": navigation_managed,
                "bond_timeout": 4.0,
                "attempt_respawn_reconnection": True,
            }],
        ),
    ]
    return LaunchDescription([
        DeclareLaunchArgument(
            "map",
            default_value="/home/jetson/project_atlas/maps/atlas_latest.yaml",
        ),
        map_server,
        amcl,
        localization_manager,
        virtual_obstacles,
        TimerAction(period=12.0, actions=navigation_nodes),
    ])
