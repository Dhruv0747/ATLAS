#!/usr/bin/env python3
"""
nav2_rover.launch.py - Custom Nav2 launch for ROVER 4WDXL60R.
NOTE: slam_toolbox is started by tortoisebot_all.launch.py - do NOT start it here.
"""
from launch import LaunchDescription
from launch_ros.actions import Node

PARAMS_FILE = '/home/jetson/project_atlas_ws/src/tortoisebot_bringup/config/nav2_params.yaml'
USE_SIM_TIME = False

def generate_launch_description():
    nav_lifecycle_nodes = [
        'controller_server',
        'planner_server',
        'behavior_server',
        'bt_navigator',
        'waypoint_follower',
    ]

    return LaunchDescription([
        Node(
            package='nav2_controller',
            executable='controller_server',
            name='controller_server',
            output='screen',
            parameters=[PARAMS_FILE, {'use_sim_time': USE_SIM_TIME}],
            remappings=[('cmd_vel', 'cmd_vel_nav')],
        ),
        Node(
            package='nav2_planner',
            executable='planner_server',
            name='planner_server',
            output='screen',
            parameters=[PARAMS_FILE, {'use_sim_time': USE_SIM_TIME}],
        ),
        Node(
            package='nav2_behaviors',
            executable='behavior_server',
            name='behavior_server',
            output='screen',
            parameters=[PARAMS_FILE, {'use_sim_time': USE_SIM_TIME}],
            remappings=[('cmd_vel', 'cmd_vel_nav')],
        ),
        Node(
            package='nav2_bt_navigator',
            executable='bt_navigator',
            name='bt_navigator',
            output='screen',
            parameters=[PARAMS_FILE, {'use_sim_time': USE_SIM_TIME}],
        ),
        Node(
            package='nav2_waypoint_follower',
            executable='waypoint_follower',
            name='waypoint_follower',
            output='screen',
            parameters=[PARAMS_FILE, {'use_sim_time': USE_SIM_TIME}],
        ),
        Node(
            package='nav2_lifecycle_manager',
            executable='lifecycle_manager',
            name='lifecycle_manager_navigation',
            output='screen',
            parameters=[
                {
                    'use_sim_time': USE_SIM_TIME,
                    'autostart': True,
                    'node_names': nav_lifecycle_nodes,
                    'bond_timeout': 4.0,
                    'attempt_respawn_reconnection': True,
                }
            ],
        ),
    ])


