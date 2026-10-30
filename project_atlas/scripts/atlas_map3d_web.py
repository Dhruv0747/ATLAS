"""Read-only stored map API; no ROS participant, camera or service controls."""
import json
import os
from pathlib import Path
import re
from urllib.parse import urlsplit,parse_qs

ROOT=Path(os.environ.get('ATLAS_MAP3D_ROOT',str(Path.home()/'.local/share/atlas/maps3d')))


def read(path,limit):
    if path.is_symlink() or path.stat().st_size>limit:raise ValueError('unsafe/oversized map artifact')
    return json.loads(path.read_bytes())


def payload(path,root=ROOT):
    p=urlsplit(path);q=parse_qs(p.query)
    if p.path=='/api/map3d/sessions':
        result=[]
        if root.exists():
            for d in sorted(root.iterdir(),reverse=True):
                if len(result)>=100:break
                if d.is_symlink() or not d.is_dir():continue
                if not re.fullmatch(r'[0-9]{8}T[0-9]{6}-[a-f0-9]{8}',d.name):continue
                try:result.append(dict(id=d.name,status=read(d/'status.json',16384)))
                except (ValueError,OSError):continue
        return {'sessions':result,'host':'Jetson local storage','read_only':True}
    if p.path=='/api/map3d/cloud':
        ident=q.get('id',[''])[0]
        if not re.fullmatch(r'[0-9]{8}T[0-9]{6}-[a-f0-9]{8}',ident):raise ValueError('invalid session id')
        d=root/ident
        if d.is_symlink():raise ValueError('symlink session rejected')
        data=read(d/'cloud.json',4*1024**2)
        if len(data.get('points',[]))>20000:raise ValueError('point budget exceeded')
        return data
    raise ValueError('unknown map route')


def serve(handler):
    if not urlsplit(handler.path).path.startswith('/api/map3d/'):return False
    try:body=json.dumps(payload(handler.path),allow_nan=False).encode();code=200
    except (OSError,ValueError,KeyError):body=b'{"error":"Stored map unavailable"}';code=404
    handler.send_response(code);handler.send_header('Content-Type','application/json')
    handler.send_header('Cache-Control','no-store');handler.send_header('X-Content-Type-Options','nosniff')
    handler.send_header('Content-Length',str(len(body)));handler.end_headers();handler.wfile.write(body)
    return True
