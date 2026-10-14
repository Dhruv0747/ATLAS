"""Analyze collapsed py-spy samples, never infer CPU time or Linux TIDs."""
import argparse,collections,json,re
from pathlib import Path

EXECUTOR_SHA256 = 'e854591961c38e95e465c2040400c18111b8b3ce445cae195345cabbaaf6c010'

def analyze(text, executor_sha256=None):
    total=0;paths=collections.Counter();leaves=collections.Counter();wait_lines=collections.Counter();phases=collections.Counter()
    for line in text.splitlines():
        if not line.strip():continue
        stack,count=line.rsplit(' ',1);count=int(count)
        if count<=0:raise ValueError('non-positive sample count')
        frames=stack.split(';');total+=count;leaf=frames[-1];leaves[leaf]+=count
        path='status' if any(f.startswith('_spin_status (atlas_status_web.py:') for f in frames) else 'main' if any(f.startswith('_spin (atlas_status_web.py:') for f in frames) else 'other'
        paths[path]+=count
        wait=[f for f in frames if f.startswith('_wait_for_ready_callbacks (rclpy/executors.py:')]
        if wait:
            line_no=int(re.search(r':(\d+)\)',wait[-1]).group(1));wait_lines[str(line_no)]+=count
            phases['inclusive_wait_generator']+=count
            if leaf.startswith('_wait_for_ready_callbacks ('):phases['leaf_wait_generator']+=count
            # These ranges must be checked against the exact installed source before interpretation.
            if executor_sha256 == EXECUTOR_SHA256:
                phases['construction' if 570<=line_no<=674 else 'wait_return_boundary_not_cpu_attribution' if line_no in (677,678) else 'readiness' if 680<=line_no<=740 else 'other_generator_line']+=count
    return {'samples':total,'call_paths':dict(paths),'categories_installed_line_mapping':dict(phases),'wait_generator_lines':dict(wait_lines),'top_leaves':leaves.most_common(20),'linux_tid_attribution':'not available in untagged collapsed stacks; call path is not a TID','warning':'sample counts are not CPU time, wait durations, wakeup counts or callback rates'}

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('profile',type=Path);p.add_argument('--executor-sha256');a=p.parse_args();print(json.dumps(analyze(a.profile.read_text(encoding='utf-8'),a.executor_sha256),indent=2))
