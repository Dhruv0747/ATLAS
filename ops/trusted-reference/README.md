# Trusted health checker reference

These files are a reviewed installation source only. GitHub Actions must never
execute this repository copy directly.

Install the checker once as root at:

/opt/atlas-ci/atlas-health-check

with root:root ownership and mode 0755, and install the sudoers rule under
/etc/sudoers.d/atlas-ci-health after validating it with visudo.

The runtime checker accepts no arguments and writes only:

/home/atlas-runner/atlas_health.json
/home/atlas-runner/atlas_health.txt

The self-hosted runner may invoke exactly:

sudo -n /opt/atlas-ci/atlas-health-check

The checker is read-only with respect to ROS and ATLAS. It uses topic list/echo
and systemd state reads only; it contains no ROS publishers, service calls,
motion commands, restarts, deployment actions, or arbitrary command input.
