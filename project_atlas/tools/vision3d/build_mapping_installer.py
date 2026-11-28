"""Offline only: build a live-byte-bound installation/rollback package."""
import argparse,base64,difflib,hashlib,json,subprocess,time
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2]
SOURCE='31b45420e14d5ebf7b9605528c31f99ae19e3293'
def digest(b):return hashlib.sha256(b).hexdigest()
def normalize(b):return b.replace(b'\r\n',b'\n')
def once(data,old,new):
    old=old.encode();new=new.encode()
    if data.count(old)!=1:raise ValueError('patch anchor missing/ambiguous: '+old[:80].decode())
    return data.replace(old,new,1)
def build(inspection,review,output):
    j=json.loads(Path(inspection).read_text());old=json.loads((Path(review)/'REVIEW_ONLY.json').read_text())
    if old['source_commit']!=SOURCE or j['host']!='jetsan-desktop':raise ValueError('identity mismatch')
    out=Path(output);out.mkdir(exist_ok=False,parents=True)
    live=j['files'];payload={};unchanged={};patches={}
    for name,h in old['files'].items():
        data=(Path(review)/name).read_bytes()
        if digest(data)!=h:raise ValueError('review artifact drift')
        blob=subprocess.check_output(['git','show',SOURCE+':project_atlas/'+name],cwd=ROOT)
        if normalize(data)!=normalize(blob):raise ValueError('source commit mismatch')
        row=live[name]
        if row['exists'] and normalize(base64.b64decode(row['bytes']))==normalize(data):
            unchanged[name]=row['sha256'];continue
        payload[name]=normalize(data)
    runtime=base64.b64decode(live['scripts/atlas_vision3d_runtime.py']['bytes'])
    original=subprocess.check_output(['git','show','be99d87:project_atlas/scripts/atlas_vision3d_runtime.py'],cwd=ROOT)
    if normalize(runtime)!=normalize(original):raise ValueError('unreviewed runtime baseline')
    name='scripts/atlas_status_web.py';data=base64.b64decode(live[name]['bytes'])
    data=once(data,'        self.tf_buffer = None','        self.rgbd_context = None\n        if os.environ.get("ATLAS_RGBD_EVIDENCE_CACHE") == "1":\n            from atlas_rgbd_context import ContextCache\n            self.rgbd_context = ContextCache()\n        self.tf_buffer = None')
    data=once(data,'            self.tf_listener = TransformListener(self.tf_buffer, self.node)','            if self.rgbd_context is None:\n                self.tf_listener = TransformListener(self.tf_buffer, self.node)\n            else:\n                from atlas_rgbd_context import listener_class\n                self.tf_listener = listener_class(TransformListener)(self.tf_buffer,self.node,self.rgbd_context)')
    for method,kind in [('_odom_cb','odom'),('_scan_cb','scan')]:
        data=once(data,'    def '+method+'(self, msg):\n','    def '+method+'(self, msg):\n        if getattr(self,"rgbd_context",None) is not None:self.rgbd_context.put("'+kind+'",msg)\n')
    data=once(data,'import atlas_vision3d_web  # Isolated read-only Vision Lab','import atlas_map3d_web  # Read-only local stored map API\nimport atlas_vision3d_web  # Isolated read-only Vision Lab')
    data=once(data,'        if atlas_vision3d_web.serve(self):','        if atlas_map3d_web.serve(self):\n            return\n        if atlas_vision3d_web.serve(self):')
    payload[name]=data
    name='scripts/atlas_web_v2.py';data=base64.b64decode(live[name]['bytes'])
    payload[name]=once(data,"PAGES = {'': 'index.html'","PAGES = {'map3d': 'map3d.html', '': 'index.html'")
    entries=[];now=time.time_ns()
    for name,data in payload.items():
        row=live[name];before=row.get('sha256');meta={k:row[k] for k in ('mode','uid','gid','atime_ns','mtime_ns','xattrs')} if before else None
        installed=meta or dict(mode=0o644,uid=1000,gid=1000,atime_ns=now,mtime_ns=now,xattrs={})
        if before:
            original=base64.b64decode(row['bytes'])
            if digest(original)!=before:raise ValueError('backup input integrity')
            p=out/'rollback'/name;p.parent.mkdir(parents=True,exist_ok=True);p.write_bytes(original)
            patches[name]=''.join(difflib.unified_diff(original.decode().splitlines(True),data.decode().splitlines(True),fromfile='a/'+name,tofile='b/'+name))
        p=out/'payload'/name;p.parent.mkdir(parents=True,exist_ok=True);p.write_bytes(data)
        entries.append(dict(path=name,before=before,after=digest(data),original=meta,installed=installed))
    for name,row in live.items():
        if name not in payload and row['exists']:unchanged[name]=row['sha256']
    support={}
    for name,data in {'stationary_gate.py':base64.b64decode(live['tools/vision3d/stationary_gate.py']['bytes']),
                      'calibration_validation.py':base64.b64decode(live['tools/vision3d/calibration_validation.py']['bytes']),
                      'install_verification.py':(ROOT/'tools/vision3d/install_verification.py').read_bytes()}.items():
        p=out/'support'/name;p.parent.mkdir(exist_ok=True);p.write_bytes(data);support[name]=digest(data)
    (out/'install_once.py').write_bytes((ROOT/'tools/vision3d/mapping_install_once.py').read_bytes())
    directories=[str(Path(p).relative_to('/home/jetson/project_atlas')).replace('\\','/') for p,v in j['parents'].items() if not v['exists']]
    existing_dirs={str(Path(p).relative_to('/home/jetson/project_atlas')).replace('\\','/'):{k:v[k] for k in ('mode','uid','gid')} for p,v in j['parents'].items() if v['exists']}
    m=dict(existing_dirs=existing_dirs,source_commit=SOURCE,activation_allowed=False,boot_id=j['boot_id'],files=entries,unchanged=unchanged,
           new_dirs=directories,unit_files=j['unit_files'],support=support,inspection_time=j['time'])
    (out/'INSTALL.json').write_text(json.dumps(m,indent=2),encoding='utf-8')
    (out/'TARGETED.patch').write_text(''.join(patches.values()),encoding='utf-8')
    checks={str(p.relative_to(out)).replace('\\','/'):digest(p.read_bytes()) for p in out.rglob('*') if p.is_file()}
    (out/'INSTALL_SHA256SUMS').write_bytes(''.join(h+'  '+n+'\n' for n,h in sorted(checks.items())).encode())
    print(json.dumps(dict(files=len(entries),replaced=sum(x['before'] is not None for x in entries),
                         added=sum(x['before'] is None for x in entries),unchanged=len(unchanged),
                         manifest_sha256=digest((out/'INSTALL.json').read_bytes()))))
if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('inspection');p.add_argument('review');p.add_argument('output');a=p.parse_args()
    build(a.inspection,a.review,a.output)
