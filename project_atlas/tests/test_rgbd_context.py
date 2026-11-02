import sys
from pathlib import Path
from types import SimpleNamespace as N
import pytest
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
from atlas_rgbd_context import ContextCache,listener_class

def message():return N(transforms=[N(header=N(frame_id='base_link'),child_frame_id='camera')])

def test_original_messages_and_receipt_freshness():
    clock=[0.];c=ContextCache(lambda:clock[0]);tf=message();scan=N(ranges=[1])
    for kind,m in [('tf',tf),('tf_static',tf),('scan',scan),('odom',object())]:c.put(kind,m)
    assert c.snapshot()['tf'][0] is tf and c.snapshot()['scan'] is scan
    clock[0]=.501
    with pytest.raises(ValueError):c.snapshot()

def test_missing_and_overflow_fail_closed():
    c=ContextCache()
    with pytest.raises(ValueError):c.snapshot()
    for _ in range(129):c.put('tf',message())
    assert len(c.dynamic)<=128
    with pytest.raises(ValueError,match='bound'):c.snapshot()

def test_existing_listener_behavior_preserved():
    calls=[]
    class Base:
        def __init__(self,b,n):calls.append(('init',b,n))
        def callback(self,m):calls.append(('tf',m))
        def static_callback(self,m):calls.append(('static',m))
    c=ContextCache();listener=listener_class(Base)('buffer','node',c);m=message()
    listener.callback(m);listener.static_callback(m)
    assert calls==[('init','buffer','node'),('tf',m),('static',m)]
    assert c.dynamic[0][1] is m and list(c.static.values())==[m]
