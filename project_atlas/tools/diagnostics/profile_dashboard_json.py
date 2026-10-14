"""Bounded native A/B response benchmark. Four GETs; no server imports or control."""
import argparse,cProfile,hashlib,json,pstats,resource,statistics,time,urllib.request
from pathlib import Path
from test_dashboard_json_cost import load_response,Sink


def main():
    p=argparse.ArgumentParser();p.add_argument('--source',type=Path,required=True);p.add_argument('--output',type=Path,required=True)
    a=p.parse_args();a.output.mkdir(exist_ok=False)
    old=load_response(a.source);new=load_response(a.source,compact=True)
    result={'source_sha256':hashlib.sha256(a.source.read_bytes()).hexdigest(),'scope':'isolated response serialization, not whole server or deployed improvement','cases':{}}
    for name in ('status','map','lidar-view','radar'):
        start=time.monotonic()
        with urllib.request.urlopen('http://127.0.0.1:8088/api/'+name,timeout=5) as r:
            body=r.read(8*1024*1024+1)
        if len(body)>8*1024*1024:raise ValueError('response too large')
        data=json.loads(body);latency=time.monotonic()-start
        (a.output/(name+'.json')).write_bytes(body) # Local diagnostic only; never commit.
        metrics={};outputs={}
        for label,fn in (('before',old),('after',new)):
            cpu=[];wall=[]
            for rep in range(5):
                t=time.monotonic();c=time.process_time()
                for _ in range(20):
                    out=Sink();fn(out,200,data)
                cpu.append((time.process_time()-c)/20);wall.append((time.monotonic()-t)/20)
            outputs[label]=out
            metrics[label]={'cpu_s_per_response':statistics.median(cpu),'wall_s_per_response':statistics.median(wall),'bytes':len(out.wfile.getvalue()),'cpu_trials_s':cpu,'wall_trials_s':wall}
        assert json.loads(outputs['before'].wfile.getvalue())==json.loads(outputs['after'].wfile.getvalue())
        assert {k:v for k,v in outputs['before'].headers.items() if k!='Content-Length'}=={k:v for k,v in outputs['after'].headers.items() if k!='Content-Length'}
        prof=cProfile.Profile();prof.enable()
        for _ in range(20):old(Sink(),200,data)
        prof.disable();prof.dump_stats(str(a.output/(name+'.prof')))
        with (a.output/(name+'-profile.txt')).open('w') as stream:pstats.Stats(prof,stream=stream).sort_stats('cumulative').print_stats(12)
        metrics['cpu_reduction_percent']=100*(1-metrics['after']['cpu_s_per_response']/metrics['before']['cpu_s_per_response'])
        metrics['single_live_get_s']=latency;metrics['decoded_equal']=True
        result['cases'][name]=metrics
    result['peak_rss_kib']=resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
    (a.output/'result.json').write_text(json.dumps(result,indent=2));print(json.dumps(result,indent=2))

if __name__=='__main__':main()
