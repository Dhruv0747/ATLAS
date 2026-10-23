"""Reuse existing QoS/shutdown scenarios against only the new offline candidate."""
import sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'tools/diagnostics'))
import benchmark_executor_accumulator as A
import test_executor_qos_shutdown_native as Q

class AccumulatorQosTests(Q.QosShutdownTests):
    def sources(self):
        return [('accumulator',A.candidate(self.raw))]
