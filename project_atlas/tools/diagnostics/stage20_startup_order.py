"""Offline ordering DAG audit; never executes systemd or starts a service."""
def cycle(edges):
    active=set();done=set();graph={}
    for earlier,later in edges:graph.setdefault(earlier,[]).append(later)
    def visit(n):
        if n in active:return True
        if n in done:return False
        active.add(n)
        if any(visit(k) for k in graph.get(n,[])):return True
        active.remove(n);done.add(n);return False
    return any(visit(n) for n in graph)

def validate(edges,requires):
    return {'ordering_cycle':cycle(edges),
        'safety_depends_on_collector':any(dependency=='atlas-checkpoint-capture.service' and
            owner in ('rover-base-telemetry.service','atlas-cmd-vel-mux.service','atlas-estop.service')
            for owner,dependency in requires),
        'collector_failure_policy':'continue existing safety startup; evidence incomplete; no fidelity permission'}
