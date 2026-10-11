#!/usr/bin/env python3
"""Adapt a generated patch to a byte-captured live baseline differing ONLY in EOL.

Refuses any content difference; never writes the live filesystem.
"""
import argparse
import difflib
from pathlib import Path
import subprocess


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--baseline', type=Path, required=True)
    parser.add_argument('--patch', type=Path, required=True)
    parser.add_argument('--path', required=True)
    parser.add_argument('--base', required=True)
    parser.add_argument('--head', required=True)
    args = parser.parse_args()
    def show(rev):
        return subprocess.check_output(['git','show',rev+':project_atlas/'+args.path])
    live, old, new = args.baseline.read_bytes(), show(args.base), show(args.head)
    normalize = lambda value: value.replace(b'\r\n',b'\n')
    assert normalize(live) == normalize(old), 'LIVE CONTENT DIFFERS: manual reconciliation required'
    diff = difflib.unified_diff(live.decode().splitlines(keepends=True),
                                new.decode().splitlines(keepends=True),
                                fromfile='a/'+args.path, tofile='b/'+args.path, n=5)
    args.patch.write_bytes(''.join(diff).encode())
    print('Verified EOL-only baseline and adapted patch:', args.path)


if __name__ == '__main__':
    main()
