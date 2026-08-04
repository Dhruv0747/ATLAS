import os
from ament_index_python.packages import get_package_share_directory
from launch import LaunchDescription
from launch_ros.actions import Node

def generate_launch_description():
    nav2_params = os.path.join(
        get_package_share_directory("tortoisebot_bringup"),
        "config", "nav2_params.yaml"
    )
    return LaunchDescription([
        Node(package="nav2_controller", executable="controller_server",
             output="screen", parameters=[nav2_params]),
        Node(package="nav2_planner", executable="planner_server",
             name="planner_server", output="screen", parameters=[nav2_params]),
        Node(package="nav2_behaviors", executable="behavior_server",
             name="behavior_server", output="screen", parameters=[nav2_params]),
        Node(package="nav2_bt_navigator", executable="bt_navigator",
             name="bt_navigator", output="screen", parameters=[nav2_params]),
        Node(package="nav2_lifecycle_manager", executable="lifecycle_manager",
             name="lifecycle_manager_navigation", output="screen",
             parameters=[{"use_sim_time": False, "autostart": True,
                          "node_names": ["controller_server","planner_server",
                                          "behavior_server","bt_navigator"]}]),
    ])
