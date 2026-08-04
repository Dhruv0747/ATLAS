# Changelog

## Unreleased

- Established a clean source-control baseline from the live ATLAS Jetson deployment.
- Added repository policy, safety exclusions, architecture overview, and development instructions.
- Approved a camera-equipped 10.1-inch CrowPanel ESP32-P4 as the removable wireless dashboard/controller replacing the broken 11-inch display; documented integration and safety requirements.
- Defined battery-powered, cable-free normal operation with automatic authenticated ATLAS discovery, reconnection, state synchronization and link-loss stopping.
- Added a read-only navigation-foundation audit identifying uncalibrated command-derived odometry, absent EKF configuration and inconsistent LiDAR/base TF definitions.
- Performed safe forward/reverse lifted-wheel encoder tests: M1 feedback passed; M2-M4 feedback was inactive and requires hardware-path inspection before odometry work.
