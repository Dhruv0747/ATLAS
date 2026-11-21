"""PC-only synthetic bounded-hash comparison; no ROS, network or hardware."""
import hashlib,json,sys,tempfile,time,tracemalloc
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[2]/'scripts'))
import atlas_vision3d_runtime as R

def main():
    with tempfile.TemporaryDirectory() as tmp:
        root=Path(tmp);entries=[]
        for i in range(458):
            data=b'x'*(16*1024*1024 if i==0 else 64)
            (root/str(i)).write_bytes(data)
            entries.append({'path':str(i),'sha256':hashlib.sha256(data).hexdigest()})
        del data
        (root/'manifest.json').write_text(json.dumps({'files':entries}))
        def original():
            manifest=json.loads((root/'manifest.json').read_text())
            assert len(manifest['files'])==458
            for f in manifest['files']:
                p=(root/f['path']).resolve()
                assert p.is_relative_to(root) and hashlib.sha256(p.read_bytes()).hexdigest()==f['sha256']
        rows=[]
        for name,fn in [('original_whole_file',original),('candidate',lambda:R.verify_runtime(root,lambda:None))]*3:
            tracemalloc.start();wall=time.monotonic();cpu=time.process_time();fn()
            row={'name':name,'cpu_s':time.process_time()-cpu,'wall_s':time.monotonic()-wall,'peak_python_bytes':tracemalloc.get_traced_memory()[1]}
            tracemalloc.stop();rows.append(row)
        print(json.dumps({'fixture':'458 files; largest16MiB; warm PC filesystem; NOT Jetson performance','measurements':rows},indent=2))
if __name__=='__main__':main()
