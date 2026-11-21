import json, time, urllib.request, math, struct
S="/home/jetson/project-atlas-migration/headroom_20261024_2122"; out=open(S+"/vl_status.jsonl","a"); raws=0; end=time.time()+300
while time.time()<end:
    t=time.time()
    try:
        j=json.loads(urllib.request.urlopen("http://127.0.0.1:8088/api/vision3d/status",timeout=2).read())
        d=j["streams"]["depth"]; rt=j.get("runtime") or {}
        row=dict(unix=round(t,2),state=rt.get("state"),depth_state=d["state"],fps=d["fps_observed"],age_s=d["age_s"],source_age_s=d["source_age_s"],received=d["received"],max_gap_s=d["max_gap_s"],w=d["width"],h=d["height"],enc=d["encoding"],astra_cpu=rt.get("astra_cpu_one_core_percent"),cpu_over=rt.get("cpu_over_limit_samples"),cpu_max=rt.get("cpu_max_percent"),policy=(rt.get("cpu_policy") or "")[:12])
        if d["state"]=="ACTIVE" and raws<3 and d.get("received",0)>20:
            r=urllib.request.urlopen("http://127.0.0.1:8088/api/vision3d/raw?kind=depth",timeout=3); b=r.read(); h=r.headers
            w,hh,step=int(h["X-Width"]),int(h["X-Height"]),int(h["X-Step"]); enc=h["X-Encoding"]
            stride=max(1,math.ceil(math.sqrt(w*hh/6000))); valid=inval=0; zs=[]
            for v in range(0,hh,stride):
                for u in range(0,w,stride):
                    raw=struct.unpack_from("<H",b,v*step+u*2)[0] if enc=="16UC1" else struct.unpack_from("<f",b,v*step+u*4)[0]
                    z=(float("nan") if raw in (0,65535) else raw/1000) if enc=="16UC1" else raw
                    if z>0 and z<=8: valid+=1; zs.append(z)
                    else: inval+=1
            zs.sort(); row["raw_frame"]=dict(bytes=len(b),w=w,h=hh,enc=enc,stamp=h.get("X-Source-Stamp"),stride=stride,points=min(valid,6000),invalid=inval,z_min=zs[0] if zs else None,z_median=zs[len(zs)//2] if zs else None,z_max=zs[-1] if zs else None)
            raws+=1
    except Exception as e: row=dict(unix=round(t,2),error=str(e)[:120])
    out.write(json.dumps(row)+"\n"); out.flush(); time.sleep(max(0,1-(time.time()-t)))
