#!/usr/bin/env python3
"""Atomically promote a validated taught-corridor map image and rebind metadata."""
import argparse
import hashlib
import json
import shutil
import time
from pathlib import Path


def atomic_json(path: Path, value: dict) -> None:
    if not path.exists():
        return
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    temporary.replace(path)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("active_yaml")
    parser.add_argument("candidate_pgm")
    parser.add_argument("--semantic", required=True)
    args = parser.parse_args()
    active_yaml = Path(args.active_yaml)
    active_pgm = active_yaml.with_suffix(".pgm")
    candidate = Path(args.candidate_pgm)
    if not active_yaml.exists() or not active_pgm.exists() or candidate.stat().st_size < 100:
        raise RuntimeError("active or candidate map is missing")
    stamp = time.strftime("%Y%m%d-%H%M%S")
    backup = active_yaml.parent / "backups" / f"taught_corridor_{stamp}"
    backup.mkdir(parents=True, exist_ok=False)
    shutil.copy2(active_yaml, backup / active_yaml.name)
    shutil.copy2(active_pgm, backup / active_pgm.name)
    staged = active_pgm.with_suffix(".pgm.taught.tmp")
    shutil.copy2(candidate, staged)
    staged.replace(active_pgm)
    digest = hashlib.sha256(active_yaml.read_bytes() + active_pgm.read_bytes()).hexdigest()[:20]
    config_root = Path.home() / ".config/project_atlas"
    for path in (
        config_root / "home_pose.json",
        config_root / "localization_seed_pose.json",
        config_root / "named_places.json",
        Path(args.semantic),
    ):
        try:
            value = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        value["map_id"] = digest
        if path.name == "named_places.json":
            for pose in value.values():
                if isinstance(pose, dict):
                    pose["map_id"] = digest
        elif path.name == "atlas_house_semantic.json":
            for pose in value.get("rooms", {}).values():
                pose["map_id"] = digest
        atomic_json(path, value)
    print(json.dumps({"map_id": digest, "backup": str(backup)}, indent=2))


if __name__ == "__main__":
    main()
