"""Read-only Astra adapters. No ROS, camera driver, servo or velocity publisher."""
import math
import time


def rgb_array(message, now_ns):
    import numpy as np
    stamp = message.header.stamp.sec*1_000_000_000 + message.header.stamp.nanosec
    if not 0 <= now_ns-stamp <= 500_000_000:
        raise ValueError('RGB source timestamp stale/future')
    w,h,step=message.width,message.height,message.step
    if message.encoding not in ('rgb8','bgr8') or not 0<w<=1920 or not 0<h<=1080:
        raise ValueError('unsupported RGB encoding/dimensions')
    if step<w*3 or len(message.data)!=step*h or len(message.data)>8_000_000:
        raise ValueError('invalid RGB payload/stride')
    image=np.frombuffer(bytes(message.data),dtype=np.uint8).reshape(h,step)[:,:w*3].reshape(h,w,3)
    if message.encoding=='bgr8':image=image[:,:,::-1]
    return image.copy(),stamp


def detections(rows, width, height, people_only=False):
    out=[]
    for row in rows[:100]:
        if len(row)!=6 or any(not math.isfinite(float(x)) for x in row):
            raise ValueError('malformed model output')
        x1,y1,x2,y2,cls,score=row
        if int(cls)!=cls or not 0<=cls<80 or not 0<=score<=1:
            raise ValueError('invalid class/confidence')
        if people_only and cls!=0:continue
        box=[max(0,min(width,float(x1))),max(0,min(height,float(y1))),
             max(0,min(width,float(x2))),max(0,min(height,float(y2)))]
        if box[2]<=box[0] or box[3]<=box[1]:continue
        out.append(dict(box=box,class_id=int(cls),label='person' if cls==0 else 'class '+str(int(cls)),
                        confidence=float(score),distance_m=None))
    return out


def iou(a,b):
    intersection=max(0,min(a[2],b[2])-max(a[0],b[0]))*max(0,min(a[3],b[3])-max(a[1],b[1]))
    union=(a[2]-a[0])*(a[3]-a[1])+(b[2]-b[0])*(b[3]-b[1])-intersection
    return intersection/union if union>0 else 0


class Tracker:
    """Bounded 2D box association, not skeletal pose or identity recognition."""
    def __init__(self):self.tracks={};self.next_id=1;self.last=None
    def update(self, rows, stamp_ns):
        if self.last is not None and stamp_ns<=self.last:raise ValueError('repeated/regressed source frame')
        self.last=stamp_ns
        self.tracks={k:v for k,v in self.tracks.items() if 0<=stamp_ns-v['stamp']<=1_000_000_000}
        unused=set(self.tracks);out=[]
        for row in rows:
            matches=[(iou(row['box'],self.tracks[k]['box']),k) for k in unused if self.tracks[k]['class_id']==row['class_id']]
            score,k=max(matches,default=(0,None))
            if score<.3:k=self.next_id;self.next_id+=1
            else:unused.remove(k)
            value=dict(row,track_id=k);out.append(value)
            self.tracks[k]=dict(value,stamp=stamp_ns)
        self.tracks=dict(list(self.tracks.items())[-100:])
        return out
