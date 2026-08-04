from setuptools import find_packages, setup
import os
from glob import glob

package_name = 'tortoisebot_control'

setup(
    name=package_name,
    version='0.0.0',
    packages=find_packages(exclude=['test']),
    data_files=[
        ('share/ament_index/resource_index/packages',
            ['resource/' + package_name]),
        ('share/' + package_name, ['package.xml']),
        (os.path.join('share', package_name, 'launch'), glob('launch/*.launch.py')),
    ],
    install_requires=['setuptools'],
    zip_safe=True,
    maintainer='dhruv',
    maintainer_email='dhruv@example.com',
    description='TortoiseBot motor control and IMU',
    license='MIT',
    tests_require=['pytest'],
    entry_points={
        'console_scripts': [
            'motor_node = tortoisebot_control.motor_node:main',
            'lidar_node = tortoisebot_control.lidar_node:main',
            'imu_node = tortoisebot_control.imu_node:main',
        ],
    },
)
