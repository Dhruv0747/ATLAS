"""Apply ONLY the new scan guard to an audited older live mux snapshot.

Generates a private candidate and patch, never edits the installed file. Avoids
pulling unrelated, undeployed AMCL code from the source branch into production.
"""
import argparse
import ast
import difflib
import hashlib
import json
from pathlib import Path

def prepare(original, source):
    def replace(text,old,new):
        if text.count(old)!=1:raise ValueError('ambiguous/missing patch anchor: '+old)
        return text.replace(old,new,1)
    if 'lidar_availability' in original:raise ValueError('guard already present')
    candidate=replace(original,'from sensor_msgs.msg import Joy\n',
        'from sensor_msgs.msg import Joy, LaserScan\nfrom atlas_lidar_availability import LidarAvailability\n')
    start=source.index("        self.declare_parameter('lidar_guard_timeout_s'")
    end=source.index('        self.declare_parameter("foxglove_max_linear"',start)
    anchor='        self.declare_parameter("nav_timeout", 0.50)\n'
    candidate=replace(candidate,anchor,anchor+source[start:end])
    tree=ast.parse(source);lines=source.splitlines(keepends=True)
    methods=[n for n in ast.walk(tree) if isinstance(n,ast.FunctionDef) and n.name in ('on_guard_scan','lidar_command_guard')]
    if len(methods)!=2:raise ValueError('guard methods missing')
    body='\n'.join(''.join(lines[n.lineno-1:n.end_lineno]) for n in methods)+'\n'
    anchor='    @staticmethod\n    def copy_twist'
    candidate=replace(candidate,anchor,body+anchor)
    anchor='            if blocked_reason:\n'
    candidate=replace(candidate,anchor,"            blocked_reason = blocked_reason or self.lidar_command_guard(\n                selected.name, selected.command, now)\n"+anchor)
    compile(candidate,'candidate_mux','exec')
    return candidate

def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--baseline',type=Path,required=True);p.add_argument('--sha256',required=True)
    p.add_argument('--source',type=Path,required=True);p.add_argument('--output',type=Path,required=True)
    a=p.parse_args();raw=a.baseline.read_bytes()
    assert hashlib.sha256(raw).hexdigest()==a.sha256,'baseline differs'
    assert not a.output.exists(),'preserve old candidate'
    original=raw.decode().replace('\r\n','\n');candidate=prepare(original,a.source.read_text())
    a.output.write_bytes(candidate.encode())
    patch=''.join(difflib.unified_diff(original.splitlines(True),candidate.splitlines(True),
        fromfile='a/scripts/atlas_cmd_vel_mux.py',tofile='b/scripts/atlas_cmd_vel_mux.py'))
    a.output.with_suffix('.patch').write_bytes(patch.encode())
    print(json.dumps({'baseline_sha256':a.sha256,'candidate_sha256':hashlib.sha256(candidate.encode()).hexdigest(),'patch_only':'LiDAR availability'}))

if __name__=='__main__':main()
