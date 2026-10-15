Throwaway read-only analysis scripts for the Stage 25 round-trip report. They hard-code the analysis
sandbox paths (bag copies under /mnt/user-data/uploads/...), need `pip install rosbags`, and skip
`/particle_cloud`. They never publish to ROS. Raw bags are not in the repo.
