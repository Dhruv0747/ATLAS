import math,numpy as np
exec(open('s25_wall.py').read().split("for topic in ('/scan','/scan_raw'):")[0])
exec("def window_scan(a,b):\n"+open('s25_wall.py').read().split("def window_scan(a,b):\n")[1].split("for label,(a,b)")[0])
rng,m=window_scan(436,450); p=pose(t0+443)
print('AMCL end',p[:3])
cand=[]
for dx in np.arange(-2.0,2.01,0.1):
    for dy in np.arange(-2.0,2.01,0.1):
        for dyaw in np.radians(np.arange(-90,91,3)):
            try: s,_=fitscore(rng,m,p[0]+dx,p[1]+dy,p[2]+dyaw)
            except Exception: s=0
            cand.append((s,dx,dy,math.degrees(dyaw)))
cand.sort(reverse=True)
print('top 8 wide-search fits (fit<=0.07, dx, dy, dyaw):')
for r in cand[:8]: print('  %.2f  dx %+.1f dy %+.1f dyaw %+.0f  -> pose (%.2f,%.2f,%.0f°)'%(r[0],r[1],r[2],r[3],p[0]+r[1],p[1]+r[2],math.degrees(p[2])+r[3]))
print('AMCL own fit %.2f'%fitscore(rng,m,*p[:3])[0])
