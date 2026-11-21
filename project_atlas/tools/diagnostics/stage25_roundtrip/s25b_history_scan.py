"""Read-only history scan (runs on the Jetson with plain sqlite3; no ROS needed).
Per bag and wheel: counted/reference ratio going forward vs in reverse, polarity inferred from the data.
Reference = median of the four polarity-corrected wheels, so one bad wheel does not set the scale.
Caveat: when two wheels are weak in the same direction the reference itself shrinks; read rows, not single numbers."""
import sqlite3,struct,glob,os,json,statistics as st
ROOT=os.path.expanduser("~/project_atlas/data"); MAXMB=350
def i32(b): return struct.unpack_from("<i",b,4)[0]
rows=[]
for p in sorted(glob.glob(ROOT+"/**/*.db3",recursive=True)):
    if os.path.getsize(p)>MAXMB*1e6 or "/input" in p or "ab_" in p.split("/")[-2] or "result_" in p: continue
    try:
        c=sqlite3.connect("file:"+p+"?mode=ro",uri=True)
        tp={n:i for i,n in c.execute("select id,name from topics")}
        need=["/yahboom/encoder/m%d"%k for k in (1,2,3,4)]
        if not all(n in tp for n in need): continue
        ids={tp[n]:k for k,n in enumerate(need)}; data={}
        for tid,t,b in c.execute("select topic_id,timestamp,data from messages where topic_id in (%s) order by timestamp"%",".join(map(str,ids))):
            data.setdefault(ids[tid],[]).append((t,i32(b)))
        if any(len(data.get(k,[]))<50 for k in range(4)): continue
        ts=[t for t,_ in data[0]]; cols=[]
        for k in range(4):
            arr=data[k]; j=0; last=arr[0][1]; out=[]
            for t in ts:
                while j<len(arr) and arr[j][0]<=t: last=arr[j][1]; j+=1
                out.append(last)
            cols.append(out)
        n=len(ts); d=[[cols[k][i+1]-cols[k][i] for i in range(n-1)] for k in range(4)]
        mv=[i for i in range(n-1) if sum(abs(d[k][i])>=6 for k in range(4))>=2]
        if len(mv)<20: continue
        def corr(a,b):
            ma=sum(a)/len(a); mb=sum(b)/len(b); sa=sum((x-ma)**2 for x in a)**.5; sb=sum((x-mb)**2 for x in b)**.5
            return 0 if sa*sb==0 else sum((x-ma)*(y-mb) for x,y in zip(a,b))/(sa*sb)
        sub=[[d[k][i] for i in mv] for k in range(4)]
        C=[[corr(sub[a],sub[b]) for b in range(4)] for a in range(4)]
        anchor=max(range(4),key=lambda a:sum(abs(C[a][b]) for b in range(4) if b!=a))
        pol=[1 if C[anchor][k]>=0 else -1 for k in range(4)]; pol[anchor]=1
        ref=[st.median([pol[k]*d[k][i] for k in range(4)]) for i in range(n-1)]
        g=1 if sum(ref)>=0 else -1
        res={"bag":os.path.relpath(p,ROOT)[:90],"min":round((ts[-1]-ts[0])/6e10,1),"moving":len(mv),"anchor":"M%d"%(anchor+1)}
        for k in range(4):
            fw=[i for i in mv if g*ref[i]>=6]; rv=[i for i in mv if g*ref[i]<=-6]
            def ratio(idx):
                if len(idx)<8: return None
                num=sum(g*pol[k]*d[k][i] for i in idx); den=sum(g*ref[i] for i in idx); return round(num/den,2) if den else None
            res["M%d"%(k+1)]={"fwd_ratio":ratio(fw),"rev_ratio":ratio(rv),"fwd_zero":round(sum(abs(d[k][i])<=1 for i in fw)/len(fw),2) if len(fw)>=8 else None,"nf":len(fw),"nr":len(rv)}
        rows.append(res)
    except Exception as e:
        rows.append({"bag":os.path.relpath(p,ROOT)[:90],"error":str(e)[:80]})
json.dump(rows,open(os.path.expanduser("~/project_atlas/data/diagnostics/stage25b_history/hist.json"),"w"),indent=1)
print("done",len(rows))
