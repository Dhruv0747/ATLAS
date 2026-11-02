"""Offline message-shaped fixtures, never real Astra evidence."""
import math
from pathlib import Path
import struct
import sys
from types import SimpleNamespace as N
import pytest
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'tools/vision3d'))
from onboard_adapter import cloud_points, ns


def cloud(big=False):
    fields=[N(name=k,offset=i*4,datatype=7,count=1) for i,k in enumerate(('x','y','z'))]
    endian='>' if big else '<'
    return N(width=1,height=2,point_step=12,row_step=16,is_bigendian=big,fields=fields,
        data=struct.pack(endian+'fff',1,2,3)+b'pad!'+struct.pack(endian+'fff',4,5,6)+b'pad!')


@pytest.mark.parametrize('big',[False,True])
def test_padded_organized_cloud_preserved(big):
    assert cloud_points(cloud(big)) == [[1,2,3],[4,5,6]]


@pytest.mark.parametrize('attr,value',[('point_step',0),('row_step',4),('width',0),('data',b'')])
def test_invalid_layout_rejected(attr,value):
    c=cloud();setattr(c,attr,value)
    with pytest.raises(ValueError):cloud_points(c)


def test_invalid_fields_and_nonfinite_points():
    c=cloud();c.fields[0].offset=12
    with pytest.raises(ValueError):cloud_points(c)
    c=cloud();c.fields[0].count=2
    with pytest.raises(ValueError):cloud_points(c)
    c=cloud();c.data=struct.pack('<fff',math.nan,2,3)+b'pad!'+c.data[16:]
    assert cloud_points(c)==[[4,5,6]]


def test_output_point_budget():
    c=cloud();c.width=40001;c.height=1;c.row_step=c.width*12
    c.data=struct.pack('<fff',1,2,3)*c.width
    assert 0<len(cloud_points(c))<=20000


@pytest.mark.parametrize('sec,nano',[(-1,0),(100,-1),(99,1000000000),(True,0)])
def test_invalid_original_stamp_rejected(sec,nano):
    with pytest.raises(ValueError):ns(N(header=N(stamp=N(sec=sec,nanosec=nano))))


def test_original_stamp_precision_preserved():
    assert ns(N(header=N(stamp=N(sec=100,nanosec=123456789))))==100123456789


def test_overlapping_fields_rejected():
    c=cloud();c.fields[1].offset=1
    with pytest.raises(ValueError,match='overlapping'):cloud_points(c)
