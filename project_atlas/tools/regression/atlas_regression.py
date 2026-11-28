#!/usr/bin/env python3
"""ATLAS automated regression suite (read-only on the live rover; replays run in isolated ROS domains). 2026-11-13.

Run on the Jetson:   python3 ~/project_atlas/tools/regression/atlas_regression.py [--full] [--json out.json]

quick (about 1 min, safe any time, nothing moves, nothing restarts):
  unit          pytest on the core-logic tests; only failures NOT in tests/regression_known_failures.txt fail the suite
  old_map       accepted map files load, their map id matches every named place, 'dhruv room' -> 'hall' is connected
                on the exact saved bytes (the same check map acceptance uses), and the localization seed is on free space
  gate_history  every stored candidate-map evidence file that was rejected is still rejected by today's gate
                (the acceptance gate was not silently weakened)
full (adds about 15-60 min of CPU on the Jetson; run with the rover parked):
  return_to_start  ICP + EKF replay (tools/localization/ekf_variants.sh) of the reference drive: the live EKF's
                   start/end closure on a drive that ended on the start mark must stay under the limit
"""
import argparse, json, math, subprocess, sys, time
from pathlib import Path

HOME = Path.home()
ROOT = HOME / "project_atlas"
sys.path.insert(0, str(ROOT / "scripts"))

UNIT_TESTS = [
    "tests/test_atlas_map_acceptance_core.py", "tests/test_mapping_guard_core.py", "tests/test_batched_spin.py",
    "tests/test_feature_on_demand_mapping.py", "tests/test_atlas_scan_self_filter.py",
    "tests/test_record_atlas_demonstration.py", "tests/test_atlas_cmd_vel_mux_mapping_limit.py",
    "tests/test_atlas_cmd_vel_mux_stop_hold.py",
]
REFERENCE_BAG = ROOT / "data/demonstrations/manual_mapping_57941c0d9709-20261113-134138"
RETURN_TO_START_LIMIT_M = 0.60   # live EKF baseline 0.45-0.47 m on this bag (2026-11-13, 3 runs)


def check_unit(repo: Path):
    tests = [t for t in UNIT_TESTS if (repo / t).exists()]
    known_file = repo / "tests/regression_known_failures.txt"
    known = {l.strip() for l in known_file.read_text().splitlines() if l.strip() and not l.startswith("#")} \
        if known_file.exists() else set()
    p = subprocess.run([sys.executable, "-m", "pytest", "-q", "-p", "no:cacheprovider", "-rf", *tests],
                       cwd=repo, capture_output=True, text=True, timeout=600)
    failed = sorted({l.split()[1] for l in p.stdout.splitlines() if l.startswith("FAILED ")})
    new = [f for f in failed if f not in known]
    summary = (p.stdout.strip().splitlines() or ["no output"])[-1]
    return not new, {"summary": summary, "new_failures": new, "known_failures_seen": len(failed) - len(new)}


def check_old_map():
    from atlas_map_acceptance_core import exact_candidate_connectivity, map_pair_id
    maps = ROOT / "maps"; y, g = maps / "atlas_latest.yaml", maps / "atlas_latest.pgm"
    places = json.loads((HOME / ".config/project_atlas/named_places.json").read_text())
    mid = map_pair_id(y, g)
    detail, ok = {"map_id": mid}, True
    named = {k: v for k, v in places.items() if isinstance(v, dict) and "x" in v}
    for name, p in named.items():
        if p.get("map_id") != mid:
            ok = False; detail[f"place_{name}"] = f"map_id {p.get('map_id')} != {mid}"
    for a, b in (("dhruv room", "hall"),):
        if a in named and b in named:
            c = exact_candidate_connectivity(y, g, named[a], named[b])
            detail[f"connected_{a}_{b}"] = c.get("passed", c.get("connected"))
            ok &= bool(detail[f"connected_{a}_{b}"])
        else:
            ok = False; detail["missing_places"] = [n for n in (a, b) if n not in named]
    return ok, detail


def check_gate_history():
    from atlas_map_acceptance_core import evaluate_acceptance_evidence
    weakened, n = [], 0
    for f in sorted((ROOT / "maps").glob(".atlas_candidate_*.acceptance.json")):
        d = json.loads(f.read_text())
        if d.get("decision") != "rejected":
            continue
        n += 1
        fails = evaluate_acceptance_evidence(
            d, expected_session_id=d["session_id"], expected_candidate_map_id=d["candidate_map_id"],
            session_started_unix=(d.get("tf_jump") or {}).get("session_started_unix", 0.0),
            evaluated_unix=d["evaluated_unix"])
        if not fails:
            weakened.append(f.name)
    return not weakened and n > 0, {"rejected_candidates_rechecked": n, "now_accepted": weakened}


def check_return_to_start():
    if not REFERENCE_BAG.exists():
        return False, {"error": f"reference bag missing: {REFERENCE_BAG}"}
    p = subprocess.run(["bash", str(ROOT / "tools/localization/ekf_variants.sh"), str(REFERENCE_BAG)],
                       capture_output=True, text=True, timeout=7200)
    out = Path(f"/tmp/ekf_variants_{REFERENCE_BAG.name}/summary.json")
    if not out.exists():
        return False, {"error": p.stdout[-400:] + p.stderr[-400:]}
    s = json.loads(out.read_text())
    live = s.get("live", {})
    ok = isinstance(live, dict) and live.get("closure_m", 99) <= RETURN_TO_START_LIMIT_M
    return ok, {"limit_m": RETURN_TO_START_LIMIT_M, "live": live,
                "others": {k: v for k, v in s.items() if k not in ("live",)}}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--full", action="store_true"); ap.add_argument("--json")
    ap.add_argument("--repo", default=str(ROOT), help="tree with scripts/ and tests/ (e.g. a staging copy)")
    a = ap.parse_args()
    repo = Path(a.repo)
    checks = [("unit", lambda: check_unit(repo)), ("old_map", check_old_map), ("gate_history", check_gate_history)]
    if a.full:
        checks.append(("return_to_start", check_return_to_start))
    results, all_ok = {}, True
    for name, fn in checks:
        t = time.time()
        try:
            ok, detail = fn()
        except Exception as exc:     # a crashing check is a failing check
            ok, detail = False, {"error": repr(exc)}
        results[name] = {"pass": bool(ok), "seconds": round(time.time() - t, 1), **detail}
        all_ok &= bool(ok)
        print(f"{'PASS' if ok else 'FAIL'}  {name:16s} {json.dumps(detail)[:300]}")
    print("ATLAS regression:", "ALL PASS" if all_ok else "FAILURES")
    if a.json:
        Path(a.json).write_text(json.dumps({"time": time.time(), "all_pass": all_ok, "results": results}, indent=1))
    sys.exit(0 if all_ok else 1)


if __name__ == "__main__":
    main()
