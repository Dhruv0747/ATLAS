"""Saved failure and clock-boundary regression; no production access."""
import sys
from pathlib import Path
from unittest.mock import patch
import pytest
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
import atlas_health_exporter as E

@pytest.mark.parametrize('stamp',[1793372301.702,1793372301.0,1793372301.999999,2147483648.125])
def test_epoch_seconds_round_trip(stamp):
    out=E.Out();out.emit('atlas_exporter_observed_timestamp_seconds',stamp)
    assert float(out.text().split()[1])==stamp

def test_saved_failure_exactly_reproduced_and_eliminated():
    stamp=1793372301.702
    assert stamp-float(f'{stamp:g}')==pytest.approx(2301.702)
    out=E.Out();out.emit('timestamp',stamp)
    assert stamp-float(out.text().split()[1])==0

@pytest.mark.parametrize('age,expected',[(0,True),(44.999,True),(45,True),(45.001,False),(60,False),(-.001,False)])
def test_fresh_stale_boundary(age,expected):
    assert E.cache_is_fresh(1000,1000+age) is expected

@pytest.mark.parametrize('stamp',[None,True,'1000',-1,float('nan'),float('inf')])
def test_missing_malformed_cache_timestamp_rejected(stamp):
    assert E.cache_is_fresh(stamp,1000) is False

def test_wall_clock_adjustment_does_not_refresh_stale_cache():
    for wall in (0,1793372301.702,9999999999):
        with patch.object(E.time,'time',return_value=wall):
            assert E.cache_is_fresh(1000,1045)
            assert not E.cache_is_fresh(1000,1045.001)

@pytest.mark.parametrize('value',[None,float('nan'),float('inf'),'not a timestamp'])
def test_missing_metric_is_omitted_not_zero(value):
    out=E.Out();out.emit('timestamp',value);assert out.text().strip()==''

def test_collect_keeps_unix_seconds_not_monotonic_or_milliseconds():
    with patch.object(E,'collect_system'),patch.object(E,'collect_units'),patch.object(E,'collect_rover'),patch.object(E.time,'time',return_value=1793372301.702),patch.object(E.time,'monotonic',side_effect=[1000,1000.125]):
        text=E.collect()
    values={k:float(v) for k,v in (line.split() for line in text.splitlines())}
    assert values['atlas_exporter_observed_timestamp_seconds']==1793372301.702
    assert values['atlas_exporter_collect_seconds']==.125

def test_large_exact_counter_preserved():
    out=E.Out();out.emit('counter',1468401);assert float(out.text().split()[1])==1468401
