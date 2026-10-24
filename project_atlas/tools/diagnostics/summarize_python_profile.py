"""Offline speedscope sample attribution; counts are NOT machine CPU percentages."""
import collections
import hashlib
import json
from pathlib import Path
import sys


def summarize(data):
    frames = data['shared']['frames']
    leaf, inclusive = collections.Counter(), collections.Counter()
    threads = []
    total = 0
    for profile in data['profiles']:
        if profile['type'] != 'sampled':
            raise ValueError('Only sampled profiles supported')
        samples = profile['samples']
        threads.append({'name': profile['name'], 'samples': len(samples)})
        total += len(samples)
        for stack in samples:
            names = [f"{frames[i]['file']}:{frames[i].get('line', 0)} {frames[i]['name']}" for i in stack]
            if names:
                leaf[names[-1]] += 1
                inclusive.update(set(names))
    return dict(samples=total, threads=threads, leaf=leaf.most_common(25),
                inclusive=inclusive.most_common(25))


if __name__ == '__main__':
    path = Path(sys.argv[1])
    raw = path.read_bytes()
    print(json.dumps(dict(sha256=hashlib.sha256(raw).hexdigest(),
                         **summarize(json.loads(raw))), indent=2))
