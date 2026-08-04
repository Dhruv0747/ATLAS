from setuptools import find_packages, setup

package_name = 'tortoisebot_motor_py'

setup(
    name=package_name,
    version='0.0.0',
    packages=find_packages(exclude=['test']),
    data_files=[
        ('share/ament_index/resource_index/packages',
            ['resource/' + package_name]),
        ('share/' + package_name, ['package.xml']),
    ],
    install_requires=['setuptools'],
    zip_safe=True,
    maintainer='dhruv',
    maintainer_email='dhruv@todo.todo',
    description='Motor driver for TortoiseBot',
    license='MIT',
    tests_require=['pytest'],
    entry_points={
        'console_scripts': [
            'motor_node = tortoisebot_motor_py.motor_node:main',
            'camera_servo_node = tortoisebot_motor_py.camera_servo_node:main',
            'ultrasonic_node = tortoisebot_motor_py.ultrasonic_node:main',
        ],
    },
)
