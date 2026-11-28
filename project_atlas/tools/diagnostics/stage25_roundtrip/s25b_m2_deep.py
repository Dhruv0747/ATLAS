"""Stage 25b: does M2 count at the same rate after its reversal (both quadrature channels alive) or not?"""
import json,numpy as np,datetime as dt
from s25_load import load
d=load({'/atlas/encoder_update'})
enc=[(t,json.loads(m.data)) for t,m,_ in d['/atlas/encoder_update']]
et=np.array([t for t,_ in enc]); R=np.array([e['raw_counts'] for _,e in enc],float); S=np.array([e['encoder_signs'] for _,e in enc])
t0=et[0]; ist=lambda t: dt.datetime.fromtimestamp(t, dt.timezone(dt.timedelta(hours=5,minutes=30))).strftime('%H:%M:%S.%f')[:-3]
dR=np.diff(R,axis=0); dts=np.diff(et); ok=dts<0.5
tm=et[1:]-t0
# fault time: M2 frozen at raw -40584 while M1 changes
i0=np.where((R[:-1,1]==-40584))[0]
print('rows with M2 raw == -40584:',len(i0),'first',ist(et[i0[0]]),'last',ist(et[i0[-1]]), 'span s %.2f'%(et[i0[-1]]-et[i0[0]]))
tf=et[i0[0]]
def seg(name,a,b):
    m=ok&(et[1:]>=a)&(et[1:]<b)
    a1,a2,a3,a4=[np.abs(dR[m,k]).sum() for k in range(4)]
    s=[(dR[m,k]*S[1:][m][:,k]).sum() for k in range(4)]   # signed, sign-corrected counts (forward-positive)
    mv=m&(np.abs(dR[:,0])>0)&(np.abs(dR[:,3])>0)
    print('%-28s |dM1|=%7.0f |dM2|=%7.0f |dM3|=%5.0f |dM4|=%7.0f  M2/M1=%.2f M2/M4=%.2f  signed(fwd+) M1 %+7.0f M2 %+7.0f M3 %+5.0f M4 %+7.0f'%(name,a1,a2,a3,a4,a2/max(a1,1),a2/max(a4,1),*s))
seg('outbound (pre-fault)',t0,t0+60)
seg('hall turn (pre-fault)',t0+60,tf-4)
seg('FROZEN window',tf,et[i0[-1]]+0.05)
seg('after fault (to end)',et[i0[-1]]+0.05,et[-1]+1)
# post-fault: split by 60s
for a in np.arange(et[i0[-1]],et[-1],60): seg('  post +%3.0fs'%(a-et[i0[-1]]),a,a+60)
# step-size distributions of M2 (non-zero deltas)
def steps(name,a,b,k):
    m=ok&(et[1:]>=a)&(et[1:]<b)&(dR[:,k]!=0)
    x=np.abs(dR[m,k]); print(name,'M%d'%(k+1),'n=%d median step %.0f p90 %.0f'%(m.sum(),np.median(x),np.percentile(x,90)))
for k in (0,1,3): steps('pre-fault ',t0,tf-4,k)
for k in (0,1,3): steps('post-fault',et[i0[-1]]+0.05,et[-1]+1,k)
# does M2 tracks M1 intra-interval? correlation of dM2 with dM1 pre/post
for nm,a,b in (('pre',t0,tf-4),('post',et[i0[-1]]+0.05,et[-1]+1)):
    m=ok&(et[1:]>=a)&(et[1:]<b)&(dR[:,0]!=0)
    c=np.corrcoef(dR[m,0]*S[1:][m][:,0],dR[m,1]*S[1:][m][:,1])[0,1]; print(nm,'corr(M1fwd,M2fwd) %.2f'%c, 'n',m.sum())
# M3 raw: how many non-zero deltas and magnitudes; raw first/last
nz=np.where(dR[:,2]!=0)[0]
print('M3 nonzero-delta intervals:',len(nz),'of',len(dR),'raw range',R[:,2].min(),R[:,2].max(),'sum|d|',np.abs(dR[:,2]).sum())
for j in nz[:12]: print('  M3',ist(et[j+1]),'d=%+.0f'%dR[j,2],'M1 d=%+.0f M4 d=%+.0f'%(dR[j,0],dR[j,3]))
print('M3 deltas when M1&M4 move >50 counts: n=%d, M3==0 in %d'%(((np.abs(dR[:,0])>50)&(np.abs(dR[:,3])>50)&ok).sum(),((np.abs(dR[:,0])>50)&(np.abs(dR[:,3])>50)&ok&(dR[:,2]==0)).sum()))
# raw wrap check
print('raw min/max per wheel',R.min(0),R.max(0))
