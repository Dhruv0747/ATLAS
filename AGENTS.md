# ATLAS engineering instructions

- Inspect relevant nodes, launch files, parameters, and current runtime evidence before editing.
- Work on one bounded feature or defect per change.
- Do not alter unrelated interfaces, topics, frames, or hardware drivers.
- Keep robot-specific tuning in YAML where practical.
- Preserve the emergency-stop priority over every velocity source.
- Never commit credentials, `.env` files, private keys, generated ROS output, models, logs, or temporary backups.
- Build affected ROS packages and run proportionate tests before committing.
- Update `README.md` and `CHANGELOG.md` when behavior or interfaces change.
- Treat the live Jetson deployment and this repository deliberately: deploy only verified changes and record what was deployed.

