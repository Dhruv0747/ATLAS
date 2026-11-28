"""Offline sweeps using installed Nav2 checker, frozen live grid and saved rays.

The synthetic grids are deliberately assumed known-free to isolate the corner
geometry. They are NOT proof of observed free space. No ROS node is created.
"""
import argparse,json,math,subprocess
from pathlib import Path
from types import SimpleNamespace as NS
import sys
sys.path.insert(0,str(Path(__file__).resolve().parents[3]/'scripts'))
from atlas_lidar_view import project

def sweep(binary,grid,base):
    results={}
    for label,v,w in [('straight',.15,0),('left',.15,.15/.35),('right',.15,-.15/.35),('reverse',-.12,0),('reverse_left',-.12,.12/.35),('stop',0,0)]:
        poses=[]
        for i in range(201):
            t=i*.02;a=w*t
            x=v*t if not w else v/w*math.sin(a)
            y=0 if not w else v/w*(1-math.cos(a))
            bx,by,ba=base;poses.append((bx+math.cos(ba)*x-math.sin(ba)*y,by+math.sin(ba)*x+math.cos(ba)*y,ba+a))
        header=[grid['width'],grid['height'],grid['resolution'],*grid['origin']]
        text=' '.join(map(str,header+grid['data']))+'\n'+'\n'.join(' '.join(map(str,p)) for p in poses)
        costs=list(map(float,subprocess.check_output([binary],input=text,text=True).split()))
        assert len(costs)==len(poses)
        collision=next((i*.02 for i,c in enumerate(costs) if c>=254),None)
        results[label]={'first_lethal_or_unknown_s':collision,'max_cost_0_8s':max(costs[:41]),'max_cost_4s':max(costs)}
    return results

def synthetic(points,unknown=False):
    w=120;res=.05;origin=-3.;data=[255 if unknown else 0]*(w*w)
    for x,y in points:
        ix,iy=int((x-origin)/res),int((y-origin)/res)
        if not (0<=ix<w and 0<=iy<w):continue
        # Explicit test fixture using configured inflation radius/scaling.
        # Not a claim that the live obstacle plugin was replayed.
        for dy in range(-6,7):
            for dx in range(-6,7):
                xx,yy=ix+dx,iy+dy;d=math.hypot(dx,dy)*res
                if 0<=xx<w and 0<=yy<w and d<=.28:
                    c=254 if d==0 else 253 if d<=.18 else int(252*math.exp(-15*(d-.18)))
                    data[yy*w+xx]=max(data[yy*w+xx],c)
    return dict(width=w,height=w,resolution=res,origin=[origin,origin],data=data)

def main():
    p=argparse.ArgumentParser();p.add_argument('--binary',required=True);p.add_argument('--capture',required=True);p.add_argument('--scans',required=True);p.add_argument('--out',required=True);a=p.parse_args()
    if Path(a.out).exists():p.error('new output required')
    cap=json.loads(Path(a.capture).read_text());scans=json.loads(Path(a.scans).read_text())
    base=next(r['local']['robot'] for r in reversed(cap['rows']) if 'robot' in r.get('local',{}))
    wall=[(2.,y/100) for y in range(-150,151,5)]
    results={'live_frozen_grid':sweep(a.binary,cap['local_grid'],base)}
    for name,pts in [('wall_only',wall),('wall_and_front_right',wall+[(.3618828573,-.358044129)]),('blocked_rear',wall+[(-.35,0)])]:results[name]=sweep(a.binary,synthetic(pts),(0,0,0))
    results['all_unknown']=sweep(a.binary,synthetic([],True),(0,0,0))
    assert results['wall_and_front_right']['straight']['first_lethal_or_unknown_s'] is None
    assert results['wall_and_front_right']['left']['first_lethal_or_unknown_s'] is None
    assert results['wall_and_front_right']['right']['first_lethal_or_unknown_s'] is not None
    assert results['blocked_rear']['reverse']['first_lethal_or_unknown_s'] is not None
    assert results['all_unknown']['reverse']['max_cost_0_8s']==255
    # Saved rays, transformed using the independently captured TF. Fixture
    # unobserved cells default free ONLY for a geometry comparison, not safety.
    saved=[]
    for sample in scans['samples']:
        s=NS(**sample['filtered_scan']);s.ranges=[float(v) for v in s.ranges]
        tr=sample['transform']
        tf=NS(translation=NS(**dict(zip('xyz',tr['translation']))),rotation=NS(**dict(zip('xyzw',tr['rotation']))))
        pts=project(s,tf)['points'];saved.append(sweep(a.binary,synthetic(pts),(0,0,0)))
    results['saved_scan_geometry']=saved
    results['fixture_assertions_passed']=5
    Path(a.out).write_text(json.dumps(results,indent=2));print(json.dumps({k:v for k,v in results.items() if k!='saved_scan_geometry'},indent=2));print('saved scans',len(saved))
if __name__=='__main__':main()
