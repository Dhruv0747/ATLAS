"""M3 parked test: Astra depth -> point cloud -> RTAB-Map (external EKF odometry). Runs in ROS domain 77 only.
Read-only for the rover: no velocity or control outputs. Started/stopped by m3_parked_test.sh."""
import os
from launch import LaunchDescription
from launch_ros.actions import Node

DB = os.environ.get('M3_DB', '/tmp/m3_test.db')
RTAB = {
    'RGBD/LinearUpdate': '0.05', 'RGBD/AngularUpdate': '0.05', 'Rtabmap/DetectionRate': '1',
    'Reg/Strategy': '1', 'Icp/VoxelSize': '0.05', 'Icp/MaxCorrespondenceDistance': '0.1', 'Icp/PointToPlane': 'false',
    'RGBD/ProximityBySpace': 'true', 'RGBD/NeighborLinkRefining': 'true',
    'Grid/Sensor': '0', 'Grid/RangeMin': '0.35', 'Grid/RangeMax': '3.0', 'Grid/CellSize': '0.05',
    'Mem/IncrementalMemory': 'true',
    # Keep a node even if it has no link yet (parked test = one node). Mapping drives link nodes anyway.
    'Mem/NotLinkedNodesKept': os.environ.get('M3_KEEP_UNLINKED', 'true'),
}


LIVE = os.path.expanduser('~/project_atlas/scripts/atlas_map3d_live.py')


def generate_launch_description():
    from launch.actions import ExecuteProcess
    return LaunchDescription([
        # Dashboard live 3D map window feed (read-only, every 3 s).
        ExecuteProcess(cmd=['python3', LIVE], output='log', name='atlas_map3d_live'),   # no respawn: session tool
        Node(package='rtabmap_util', executable='point_cloud_xyz', name='astra_cloud', output='log',
             parameters=[{'decimation': 1, 'voxel_size': 0.03, 'min_depth': 0.35, 'max_depth': 3.0,
                          'approx_sync': False}],
             remappings=[('depth/image', '/astra/depth/image_raw'), ('depth/camera_info', '/astra/depth/camera_info'),
                         ('cloud', '/astra/depth_cloud')]),
        Node(package='rtabmap_slam', executable='rtabmap', name='rtabmap', output='log', arguments=['-d'],
             parameters=[{'frame_id': 'base_link', 'subscribe_depth': False, 'subscribe_rgb': False,
                          'subscribe_rgbd': False, 'subscribe_scan_cloud': True, 'approx_sync': True,
                          'sync_queue_size': 10, 'wait_for_transform': 0.3, 'database_path': DB,
                          'publish_tf': False}, RTAB],
             remappings=[('scan_cloud', '/astra/depth_cloud'), ('odom', '/odom')]),
    ])
