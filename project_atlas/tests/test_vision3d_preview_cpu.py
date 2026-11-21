"""Bit-identical preview regression against an independent old pixel loop."""
import math,struct,sys,unittest
from pathlib import Path
from types import SimpleNamespace as NS
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
import atlas_vision3d_core as C

def frame(encoding='16UC1',big=False,w=160,h=120,padding=4):
    values=[0,1,999,1000,5000,65535] if encoding=='16UC1' else [0.,-1.,float('nan'),float('inf'),.001,1.,5.,9.]
    fmt=('>' if big else '<')+('H' if encoding=='16UC1' else 'f')
    bpp=struct.calcsize(fmt)
    row=b''.join(struct.pack(fmt,values[x%len(values)]) for x in range(w))+b'\0'*padding
    return NS(width=w,height=h,step=w*bpp+padding,data=row*h,encoding=encoding,is_bigendian=big)

def reference(m,kind='depth',max_width=240):
    C.image_layout(m);stride=max(1,math.ceil(m.width/max_width),math.ceil(m.height/180))
    xs=range(0,m.width,stride);ys=range(0,m.height,stride);rows=[];valid=invalid=0
    for y in ys:
        row=bytearray()
        for x in xs:
            z=C.depth_at(m,x,y)
            if z is None:rgb=(0,0,0);invalid+=1
            else:
                t=min(1.,z/5.);rgb=(int(255*(1-t)),int(255*(1-abs(2*t-1))),int(255*t));valid+=1
            row.extend(rgb)
        rows.append(bytes(row))
    return C._png(len(xs),len(ys),rows),dict(sampled_valid=valid,sampled_invalid=invalid,sample_stride=stride,source_width=m.width,source_height=m.height)

class PreviewCPU(unittest.TestCase):
    def test_equivalent_endian_encoding_padding_and_sampling(self):
        for enc in ('16UC1','32FC1'):
            for big in (False,True):
                for size in ((160,120),(641,481)):
                    with self.subTest(enc=enc,big=big,size=size):
                        m=frame(enc,big,*size);self.assertEqual(reference(m),C.preview(m,'depth'))
    def test_one_layout_validation(self):
        with patch.object(C,'image_layout',wraps=C.image_layout) as check:
            C.preview(frame(),'depth');self.assertEqual(check.call_count,1)
    def test_invalid_buffer_rejected(self):
        m=frame();m.data=m.data[:-1]
        with self.assertRaises(ValueError):C.preview(m,'depth')
    def test_wrong_encoding_rejected(self):
        m=NS(width=1,height=1,step=1,data=b'\0',encoding='mono8',is_bigendian=False)
        with self.assertRaises(ValueError):C.preview(m,'depth')
    def test_measurement_still_validates(self):
        m=frame();m.step=0
        with self.assertRaises(ValueError):C.depth_at(m,0,0)

if __name__=='__main__':unittest.main()
