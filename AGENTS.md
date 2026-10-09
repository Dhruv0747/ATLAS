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

## Historical failure investigation

- Before diagnosing a recurring ATLAS failure, read `docs/audits/ATLAS_CURRENT_BLOCKERS.md` and match it against `docs/audits/ATLAS_ROOT_CAUSE_REGISTRY.json`.
- Append dated evidence, triggering events, hardware/configuration identity, attempted fixes and rejected experiments. Preserve older findings and explicitly mark evidence gaps; do not overwrite failed attempts with later success claims.
- Separate confirmed observations, suspected causes, unresolved validation and scoped verified fixes. A commit, unit test or one fresh sample alone is not a physical reliability pass.
- Use saved recordings before asking for repeated manual routes. Do not repeat rejected tuning without new discriminating evidence, or restart services just to create activity.
- Keep the master analysis, timeline and blockers consistent when findings materially change. Publish coherent milestones; never publish credentials, raw private conversations or generated logs.
- This workflow does not authorize movement, flashing, calibration changes, safety bypasses or unattended background work.

