from pathlib import Path
import sys
sys.path.insert(0,str(Path(__file__).parents[1]/'tools/diagnostics/stm32_readback'))
from analyze_restart_cpu import summarize

def test_single_spike_not_inferred_transient_or_attributed():
 r=summarize([{'monotonic':1,'cpu_pct':60},{'monotonic':8,'cpu_pct':98.84}],[])
 assert r['samples'][1]['over_75']
 assert r['duration'].startswith('UNKNOWN') and r['process_attribution'].startswith('UNKNOWN')
 assert r['retry_recommendation'].startswith('NO-GO')

def test_threshold_not_averaged():
 r=summarize([{'monotonic':1,'cpu_pct':75},{'monotonic':2,'cpu_pct':75.01}],[])
 assert [x['over_75'] for x in r['samples']]==[False,True]

def test_journal_monotonic_units():
 r=summarize([],[{'__MONOTONIC_TIMESTAMP':'3681278143','MESSAGE':'atlas-sensor-recovery.service: Consumed 3.040s CPU time.'}])
 assert r['events'][0]['monotonic']==3681.278143

def test_no_samples_does_not_pass():
 assert summarize([],[])['retry_recommendation'].startswith('NO-GO')
