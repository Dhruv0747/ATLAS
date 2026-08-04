from setuptools import setup

package_name = 'atlas_gnss_driver'

setup(
    name=package_name,
    version='0.1.0',
    packages=[package_name],
    data_files=[
        ('share/ament_index/resource_index/packages',
            ['resource/' + package_name]),
        ('share/' + package_name, ['package.xml']),
    ],
    install_requires=['setuptools'],
    zip_safe=True,
    maintainer='jetson',
    maintainer_email='jetson@project-atlas.local',
    description='Raw NMEA GNSS driver for SIM8230G on Project ATLAS',
    license='Apache-2.0',
    entry_points={
        'console_scripts': [
            'gnss_node = atlas_gnss_driver.gnss_node:main',
        ],
    },
)
