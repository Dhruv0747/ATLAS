import json,glob,statistics as S,sys
for f in sorted(glob.glob(sys.argv[1])):
    d=json.load(open(f)); rows=d['rows']; pairs=sorted({r['pair'] for r in rows}); by={(r['pair'],r['variant']):r for r in rows}
    assert all(r['done']==d['args']['cycles'] for r in rows)
    print('%s py%s mode=%s  executor-thread CPU per cycle (us): v0 median %.0f'%(f.split('/')[-1],d['python'],d['args']['mode'],S.median(by[(p,'v0')]['cpu_us_per_cycle'] for p in pairs)))
    for v in ('v1','v2','v3'):
        sav=[100*(1-by[(p,v)]['cpu_us_per_cycle']/by[(p,'v0')]['cpu_us_per_cycle']) for p in pairs]
        us=[by[(p,'v0')]['cpu_us_per_cycle']-by[(p,v)]['cpu_us_per_cycle'] for p in pairs]
        wl=[100*(1-by[(p,v)]['wall_us_per_cycle']/by[(p,'v0')]['wall_us_per_cycle']) for p in pairs]
        print('   %s CPU saving median %5.1f%% [%5.1f .. %5.1f] %2d/%d pairs better | saved %.0f us/cycle | wall saving median %5.1f%%'%(v,S.median(sav),min(sav),max(sav),sum(s>0 for s in sav),len(sav),S.median(us),S.median(wl)))
