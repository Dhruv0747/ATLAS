# Mapping31b4542 installation-only preparation

Preparation PASS; GO for a separately approved installation-only transaction,
conditional on the installer fresh safety/identity checks. No execution authorized.

Read-only Jetson inspection: aarch64, Python3.10.12, ROS2Humble service environment.
2026-11-02 14:02:01 IST final comparison: all captured bytes/metadata and user service
identities unchanged. Web PID2182 and Recovery PID2089, zero restarts.

The installer replaces only live-derived atlas_status_web.py, atlas_web_v2.py and
reviewed atlas_vision3d_runtime.py; adds17 missing local mapping files and one parent
directory. Four existing dependencies differ only in newline encoding and remain
untouched. Nine dependencies/UI files are pinned read-only. No homepage, Vision Lab,
material.css, systemd configuration, environment or firewall changes.

Exact private backup bytes and metadata are bundled locally, outside Git, with
INSTALL.json, TARGETED.patch and INSTALLATION.md. The generic installer source and
builder are in project_atlas/tools/vision3d. No raw live files/logs were committed.

32 focused offline tests PASS, including failure after eachof20 writes, archive
integrity prerequisites, original byte/metadata/xattr restoration, interruption,
permission/symlink drift, stale observation and final concurrent edit rejection.
Full install/rollback and xattrs additionally PASS as Linux UID1000. Independent
review PASS after fixing safety-age and final-target verification. Existing mapping
71-test evidence reused; no unrelated suites or runtime camera tests repeated.

The command is single-use, checks live baseline and strict CPU<75/RAM<80/temp<70
safety before writes, and restores files on caught failure without service control.
Rollback refuses later owner edits. Power loss/SIGKILL require the documented manual
file rollback; no reboot or physical reliability claim. Camera/AI remainOFF; cache
activation remains disabled, mapping enabled=false. Any web reload/restart needs
separate approval; calibration/TF and live capture are not approved.
