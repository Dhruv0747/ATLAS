#!/usr/bin/env python3
"""Check experiment invariants, not autonomous-navigation acceptance."""
import argparse
import json
import math
from pathlib import Path


def validate(document):
    rows = document["results"]
    assert len(rows) == 12, "four policies x three seeds required"
    assert {(r["mode"], r["seed"]) for r in rows} == {
        (mode, seed) for mode in ("baseline", "ess_half", "no_resample", "fixed_prior")
        for seed in (1, 7, 42)}
    initial = rows[0]["initial"]
    updates = rows[0]["updates"]
    assert updates > 0
    for row in rows:
        assert row["initial"] == initial, "A/B initial states differ"
        assert row["updates"] == updates == len(row["trajectory"])
        assert row["final"] == row["trajectory"][-1]
        times = [r["time_s"] for r in row["trajectory"]]
        assert all(b > a for a, b in zip(times, times[1:]))
        if row["mode"] == "baseline":
            assert row["resamples"] == updates
        if row["mode"] in ("no_resample", "fixed_prior"):
            assert row["resamples"] == 0
        for point in row["trajectory"]:
            assert all(math.isfinite(v) for v in point["pose"])
            assert 1 - 1e-6 <= point["weight_ess"] <= point["particle_count"] + 1e-6
            assert 1 - 1e-6 <= point["geometric_ess"] <= point["geometric_support"] + 1e-6
            assert point["geometric_support"] <= initial["geometric_support"]
            if row["mode"] in ("no_resample", "fixed_prior"):
                assert point["geometric_support"] == initial["geometric_support"]
        assert row["last_scan_score_at_final"] > 0
        assert row["last_scan_score_at_initial"] > 0
    # Policies without sampling must be independent of RNG seed.
    for mode in ("no_resample", "fixed_prior"):
        trajectories = [r["trajectory"] for r in rows if r["mode"] == mode]
        assert all(t == trajectories[0] for t in trajectories)
    return len(rows)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("results", nargs="+")
    parser.add_argument("--repeat", help="Independent rerun of the first result for RNG reproducibility")
    args = parser.parse_args()
    documents = [json.loads(Path(p).read_text()) for p in args.results]
    count = sum(validate(d) for d in documents)
    if args.repeat:
        repeated = json.loads(Path(args.repeat).read_text())
        validate(repeated)
        assert documents[0]["results"] == repeated["results"], "same-seed repeat differs"
    print(f"PASS: {count} policy/seed runs across {len(documents)} stationary windows; "
          f"repeat_checked={bool(args.repeat)}. This validates the experiment, not localization accuracy.")
