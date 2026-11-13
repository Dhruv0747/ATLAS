import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

from atlas_mapping_guard_core import GuardSample, MappingGuard, cpu_idle_fraction  # noqa: E402


def ok(now, idle=0.3, load=2.0, **kw):
    v = dict(now=now, scan_age_s=0.1, wheel_odom_age_s=0.1, slam_tf_age_s=0.05,
             cpu_idle_fraction=idle, load1_per_core=load)
    v.update(kw)
    return GuardSample(**v)


def test_disarmed_never_trips():
    g = MappingGuard()
    assert g.update(ok(100.0, scan_age_s=None)) is None


def test_startup_grace_then_stale_scan_trips_once():
    g = MappingGuard(); g.arm(0.0)
    assert g.update(ok(5.0, scan_age_s=9.0)) is None          # inside grace
    r = g.update(ok(11.0, scan_age_s=2.5))
    assert r and "LiDAR scan stale" in r
    assert g.update(ok(12.0, scan_age_s=3.5)) is None          # same episode: no repeat
    assert g.update(ok(13.0)) is None                          # cleared
    assert "wheel odometry" in g.update(ok(14.0, wheel_odom_age_s=2.0))
    assert len(g.trips) == 2


def test_missing_slam_tf_trips():
    g = MappingGuard(); g.arm(0.0)
    assert "SLAM map->odom missing" in g.update(ok(11.0, slam_tf_age_s=None))


def test_cpu_overload_needs_sustained_window():
    g = MappingGuard(); g.arm(0.0)
    t, tripped = 0.0, None
    while t < 40.0 and tripped is None:
        t += 1.0
        tripped = g.update(ok(t, idle=0.02, load=7.0))
    assert tripped and "CPU overload" in tripped
    assert t >= 19.0                                           # not on the first busy second


def test_short_cpu_spike_does_not_trip():
    g = MappingGuard(); g.arm(0.0)
    for t in range(1, 60):
        busy = 20 <= t < 30                                     # 10 s spike inside a healthy run
        assert g.update(ok(float(t), idle=0.02 if busy else 0.3, load=7.0 if busy else 2.0)) is None


def test_cpu_idle_fraction():
    assert cpu_idle_fraction(None, [1] * 10) is None
    prev = [100, 0, 100, 700, 100, 0, 0, 0, 0, 0]
    cur = [200, 0, 200, 750, 100, 0, 0, 0, 0, 0]
    assert abs(cpu_idle_fraction(prev, cur) - 50 / 250) < 1e-9
