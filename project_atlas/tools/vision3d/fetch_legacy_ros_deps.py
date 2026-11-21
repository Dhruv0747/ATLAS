"""PC-only download of the three already commissioned private ROS dependencies."""
import hashlib
from pathlib import Path
import urllib.request

PACKAGES={
 'ros-humble-camera-calibration-parsers_3.1.13-1jammy.20260908.011532_arm64.deb':'d15f5580bac98a4e1722f85b9c1554083fddddffd645a9e3fc1d3dfec9513517',
 'ros-humble-camera-info-manager_3.1.13-1jammy.20260908.011907_arm64.deb':'a19b14df964131d2a38f3e87eecb253e0e56c273109c609580694510f46ddf95',
 'ros-humble-image-publisher_3.0.9-1jammy.20260908.085505_arm64.deb':'da98936b7714b656c4d1034f7dda449dbe6d96598a88e72a2e351ee4f50b7cbf'}


def main():
    dest=Path('/root/atlas-stage29/apt/archives')
    for name,expected in PACKAGES.items():
        path=dest/name
        if path.exists():data=path.read_bytes()
        else:
            package=name.split('_')[0]
            # Official apt endpoint; bytes must match the previously verified SHA256.
            # No TLS verification is disabled or system trust configuration changed.
            url='http://packages.ros.org/ros2/ubuntu/pool/main/r/'+package+'/'+name
            data=urllib.request.urlopen(url,timeout=30).read()
        if hashlib.sha256(data).hexdigest()!=expected:raise RuntimeError('package checksum mismatch '+name)
        if not path.exists():path.write_bytes(data)
        print('VERIFIED',name,expected)


if __name__=='__main__':main()
