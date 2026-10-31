"""Preserve already-acquired rejected counters; never poll more sources on failure."""
from restart_policy import save

def record_cpu_rejection(root, before, after, started, finished, cpu):
    # Signal failure first so the independent controller can stop immediately.
    save(root/'health.json',{'mono':finished,'safe':False,'error':'CPU guard '+str(cpu)})
    save(root/'rejected-cpu.json',{'before_ticks':before,'after_ticks':after,
        'started_mono':started,'finished_mono':finished,'interval_s':finished-started,
        'cpu_pct':cpu,'process_attribution':'UNAVAILABLE: no same-window process counters',
        'decision':'ABORT','retry':False})
