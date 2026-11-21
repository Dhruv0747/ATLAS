"""Exercise real response functions without importing/starting the ROS web server."""
import ast
import io
import json
import math
from pathlib import Path
import unittest


def load_response(path, compact=False):
    tree=ast.parse(Path(path).read_text(encoding='utf-8'))
    nodes=[n for n in tree.body if isinstance(n,ast.FunctionDef) and n.name in ('clean_json','json_response')]
    if len(nodes)!=2:raise ValueError('expected exact response functions')
    if compact:
        for node in ast.walk(nodes[1]):
            if isinstance(node,ast.Call) and isinstance(node.func,ast.Attribute) and node.func.attr=='dumps':
                node.keywords=[k for k in node.keywords if k.arg not in ('indent','separators')]
                node.keywords.append(ast.keyword(arg='separators',value=ast.Tuple(elts=[ast.Constant(','),ast.Constant(':')],ctx=ast.Load())))
    namespace={'json':json,'math':math}
    exec(compile(ast.fix_missing_locations(ast.Module(body=nodes,type_ignores=[])),str(path),'exec'),namespace)
    return namespace['json_response']


class Sink:
    def __init__(self):self.wfile=io.BytesIO();self.headers={};self.status=None
    def send_response(self,value):self.status=value
    def send_header(self,key,value):self.headers[key]=value
    def end_headers(self):pass


class ResponseTests(unittest.TestCase):
    def setUp(self):
        self.path=Path(__file__).resolve().parents[2]/'scripts/atlas_status_web.py'
        self.response=load_response(self.path)
    def test_payload_and_headers(self):
        data={'text':'हिंदी / English','nan':float('nan'),'inf':float('inf'),'tuple':(1,2),'age':.02,'zero':0,'stop':True}
        out=Sink();self.response(out,503,data)
        self.assertEqual(json.loads(out.wfile.getvalue()),{'text':data['text'],'nan':None,'inf':None,'tuple':[1,2],'age':.02,'zero':0,'stop':True})
        self.assertEqual(out.status,503)
        self.assertEqual(int(out.headers['Content-Length']),len(out.wfile.getvalue()))
        self.assertEqual(out.headers['Content-Type'],'application/json')
        self.assertIn('no-store',out.headers['Cache-Control'])
        self.assertEqual(out.headers['Pragma'],'no-cache')
        self.assertTrue(math.isnan(data['nan']))
    def test_no_stale_response_cache(self):
        data={'ros':{'cmd_vel':{'age':.1,'value':{'lin':0}}}}
        a=Sink();self.response(a,200,data)
        data['ros']['cmd_vel']['age']=3.5
        b=Sink();self.response(b,200,data)
        self.assertNotEqual(a.wfile.getvalue(),b.wfile.getvalue())
    def test_compact_and_equivalent_nested_payload(self):
        data={'samples':[{'value':i/10,'age':i,'valid':True} for i in range(100)]}
        out=Sink();self.response(out,200,data)
        self.assertEqual(json.loads(out.wfile.getvalue()),data)
        self.assertLess(len(out.wfile.getvalue()),len(json.dumps(data,indent=2)))
        self.assertNotIn(b'\n',out.wfile.getvalue())

if __name__=='__main__':unittest.main()
