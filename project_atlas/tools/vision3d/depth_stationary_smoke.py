"""One stationary vendor OpenNI2 depth test; statistics only, no ROS or recording.

C ABI declarations follow the pinned vendor OniCTypes.h/OniCAPI.h (OpenNI2.3).
Not a replacement ROS driver and not a calibration/obstacle-avoidance pass.
"""
import argparse
import ctypes as C
import json
import os
from pathlib import Path
import signal
import subprocess
import sys
import time
import stationary_gate as gate
from bounded_process import OwnedPacer

STAGE=Path('/home/jetson/project-atlas-migration/astra-20261021')
REDIST=STAGE/'ws/src/ros2_astra_camera/astra_camera/openni2_redist/arm64'


def parse_vendor_result(stdout):
    """Accept one complete result line, retaining native SDK messages separately."""
    records=[];messages=[]
    for line in stdout.splitlines():
        if not line.strip():continue
        if line.lstrip().startswith('{'):
            item=json.loads(line)
            if item.get('kind')!='REAL ASTRA DEPTH; no saved frames':
                raise ValueError('unexpected vendor result kind')
            records.append(item)
        else:messages.append(line)
    if len(records)!=1:raise ValueError('expected exactly one depth result')
    result=records[0];frames=result.get('frames',[])
    if len(frames)!=15:raise ValueError('incomplete depth batch')
    mode=result['selected_mode']
    choose_mode([Mode(mode['pixelFormat'],mode['resolutionX'],mode['resolutionY'],mode['fps'])])
    if any((f['width'],f['height'])!=(mode['resolutionX'],mode['resolutionY']) for f in frames):
        raise ValueError('frame dimensions differ from selected mode')
    for previous,current in zip(frames,frames[1:]):
        if current['sdk_timestamp_us']<=previous['sdk_timestamp_us'] or current['frame_index']<=previous['frame_index']:
            raise ValueError('nonmonotonic depth batch')
    if not any(f['sampled_valid']>0 for f in frames):raise ValueError('no valid sampled depth')
    return result,messages


class Mode(C.Structure):
    _fields_=[('pixelFormat',C.c_int),('resolutionX',C.c_int),('resolutionY',C.c_int),('fps',C.c_int)]
    def value(self):return {n:getattr(self,n) for n,_ in self._fields_}


class Sensor(C.Structure):
    _fields_=[('sensorType',C.c_int),('numSupportedVideoModes',C.c_int),('pSupportedVideoModes',C.POINTER(Mode))]


class DeviceInfo(C.Structure):
    _fields_=[('uri',C.c_char*256),('vendor',C.c_char*256),('name',C.c_char*256),('usbVendorId',C.c_uint16),('usbProductId',C.c_uint16)]


class Frame(C.Structure):
    _fields_=[('dataSize',C.c_int),('data',C.c_void_p),('sensorType',C.c_int),('timestamp',C.c_uint64),
              ('frameIndex',C.c_int),('width',C.c_int),('height',C.c_int),('videoMode',Mode),
              ('croppingEnabled',C.c_int),('cropOriginX',C.c_int),('cropOriginY',C.c_int),('stride',C.c_int)]


def choose_mode(modes):
    allowed=[m for m in modes if m.pixelFormat==100 and 0<m.resolutionX<=640 and 0<m.resolutionY<=480 and 0<m.fps<=30]
    if not allowed:raise RuntimeError('No advertised bounded depth mode (1mm, <=640x480, <=30Hz)')
    return min(allowed,key=lambda m:m.resolutionX*m.resolutionY*m.fps)


def child():
    if C.sizeof(C.c_void_p)!=8 or C.sizeof(Mode)!=16 or C.sizeof(DeviceInfo)!=772 or C.sizeof(Frame)!=80:
        raise RuntimeError('OpenNI ABI layout mismatch')
    sdk=C.CDLL(str(REDIST/'libOpenNI2.so'))
    def bind(n,args,ret=C.c_int):
        f=getattr(sdk,n);f.argtypes=args;f.restype=ret;return f
    ptr=C.c_void_p
    bind('oniInitialize',[C.c_int]);bind('oniShutdown',[],None)
    bind('oniGetExtendedError',[],C.c_char_p)
    bind('oniGetDeviceList',[C.POINTER(C.POINTER(DeviceInfo)),C.POINTER(C.c_int)])
    bind('oniReleaseDeviceList',[C.POINTER(DeviceInfo)])
    bind('oniDeviceOpen',[C.c_char_p,C.POINTER(ptr)]);bind('oniDeviceClose',[ptr])
    bind('oniDeviceGetSensorInfo',[ptr,C.c_int],C.POINTER(Sensor))
    bind('oniDeviceCreateStream',[ptr,C.c_int,C.POINTER(ptr)])
    bind('oniStreamSetProperty',[ptr,C.c_int,ptr,C.c_int]);bind('oniStreamGetProperty',[ptr,C.c_int,ptr,C.POINTER(C.c_int)])
    bind('oniStreamStart',[ptr]);bind('oniStreamStop',[ptr],None);bind('oniStreamDestroy',[ptr],None)
    bind('oniWaitForAnyStream',[C.POINTER(ptr),C.c_int,C.POINTER(C.c_int),C.c_int])
    bind('oniStreamReadFrame',[ptr,C.POINTER(C.POINTER(Frame))]);bind('oniFrameRelease',[C.POINTER(Frame)],None)
    bind('oniSetLogFileOutput',[C.c_int]);bind('oniSetLogConsoleOutput',[C.c_int])
    def ok(rc):
        if rc!=0:raise RuntimeError('OpenNI status '+str(rc)+': '+str(sdk.oniGetExtendedError()))
    device=ptr();stream=ptr();listing=C.POINTER(DeviceInfo)();count=C.c_int();initialized=False;started=False
    try:
        sdk.oniSetLogFileOutput(0);sdk.oniSetLogConsoleOutput(0)
        ok(sdk.oniInitialize(2003));initialized=True;ok(sdk.oniGetDeviceList(C.byref(listing),C.byref(count)))
        if not 0<=count.value<=16:raise RuntimeError('invalid device count')
        found=[listing[i] for i in range(count.value) if (listing[i].usbVendorId,listing[i].usbProductId)==(0x2bc5,0x0403)]
        if len(found)!=1:raise RuntimeError('exact single Astra depth device not enumerated')
        identity={k:getattr(found[0],k).decode(errors='replace') for k in ('uri','vendor','name')}
        print(json.dumps({'phase':'device selected','identity':identity}),file=sys.stderr,flush=True)
        ok(sdk.oniDeviceOpen(found[0].uri,C.byref(device)))
        info=sdk.oniDeviceGetSensorInfo(device,3)
        if not info or not 0<info.contents.numSupportedVideoModes<=256:raise RuntimeError('depth modes unavailable')
        modes=[Mode.from_buffer_copy(info.contents.pSupportedVideoModes[i]) for i in range(info.contents.numSupportedVideoModes)]
        selected=choose_mode(modes);ok(sdk.oniDeviceCreateStream(device,3,C.byref(stream)))
        ok(sdk.oniStreamSetProperty(stream,3,C.byref(selected),C.sizeof(selected)))
        actual=Mode();size=C.c_int(C.sizeof(actual));ok(sdk.oniStreamGetProperty(stream,3,C.byref(actual),C.byref(size)))
        if actual.value()!=selected.value():raise RuntimeError('depth mode mismatch')
        print(json.dumps({'phase':'depth mode accepted','mode':actual.value(),'advertised':[m.value() for m in modes]}),file=sys.stderr,flush=True)
        ok(sdk.oniStreamStart(stream));started=True;frames=[];previous=None;times=[]
        for i in range(15):
            index=C.c_int();streams=(ptr*1)(stream);ok(sdk.oniWaitForAnyStream(streams,1,C.byref(index),2000))
            f=C.POINTER(Frame)();ok(sdk.oniStreamReadFrame(stream,C.byref(f)))
            try:
                x=f.contents
                if not (x.sensorType==3 and 0<x.width<=640 and 0<x.height<=480 and x.stride>=x.width*2 and x.dataSize==x.stride*x.height and x.data):
                    raise RuntimeError('invalid depth frame layout')
                if x.videoMode.pixelFormat!=100 or (previous is not None and x.timestamp<=previous):raise RuntimeError('depth units/timestamp invalid')
                previous=x.timestamp
                vals=[]
                for y in range(0,x.height,8):
                    row=(C.c_uint16*x.width).from_address(x.data+y*x.stride)
                    vals.extend(row[k] for k in range(0,x.width,8))
                valid=[v for v in vals if v not in (0,65535)];times.append(time.monotonic())
                frames.append({'frame_index':x.frameIndex,'sdk_timestamp_us':x.timestamp,'width':x.width,'height':x.height,
                               'sampled_valid':len(valid),'sampled_invalid':len(vals)-len(valid),'sample_stride':8,
                               'min_depth_m':min(valid)/1000 if valid else None,'max_depth_m':max(valid)/1000 if valid else None})
            finally:sdk.oniFrameRelease(f)
        if not any(f['sampled_valid'] for f in frames):raise RuntimeError('all sampled depth pixels invalid')
        print(json.dumps({'kind':'REAL ASTRA DEPTH; no saved frames','identity':identity,'selected_mode':selected.value(),
                          'frames':frames,'observed_receive_hz':(len(times)-1)/(times[-1]-times[0]),
                          'sdk_clock_alignment':'UNKNOWN; not ROS timestamps','depth_accuracy':'NOT calibrated against physical reference'}),flush=True)
    finally:
        if started:sdk.oniStreamStop(stream)
        if stream:sdk.oniStreamDestroy(stream)
        if device:sdk.oniDeviceClose(device)
        if listing:sdk.oniReleaseDeviceList(listing)
        if initialized:sdk.oniShutdown()


def main():
    p=argparse.ArgumentParser();p.add_argument('--approve-stationary-depth',action='store_true');p.add_argument('--child',action='store_true');a=p.parse_args()
    if a.child:return child()
    if not a.approve_stationary_depth:raise SystemExit('Explicit stationary opt-in required')
    target=STAGE/'depth_stationary_result.json'
    if target.exists():raise SystemExit('existing evidence preserved; no automatic repeat')
    result={'result':'BLOCKED','samples':[],'recording':False};proc=pacer=None
    try:
        rows,before=gate.preflight();result.update(preflight=rows,units_before=before)
        proc=subprocess.Popen([sys.executable,__file__,'--child'],stdout=subprocess.PIPE,stderr=subprocess.PIPE,start_new_session=True,cwd=str(STAGE))
        pacer=OwnedPacer(proc).start();start=time.monotonic();last=gate.ticks()
        while proc.poll() is None:
            if time.monotonic()-start>20:raise RuntimeError('20-second depth deadline')
            if pacer.error:raise RuntimeError('owned pacer failed')
            time.sleep(.5);now=gate.ticks();result['samples'].append(gate.check(gate.cpu_delta(last,now)));last=now
            if gate.services()!=before:raise RuntimeError('essential identity changed')
        stdout,stderr=proc.communicate(timeout=1)
        if proc.returncode!=0:raise RuntimeError('depth child failed: '+stderr.decode(errors='replace')[-1000:])
        result['camera'],result['sdk_messages']=parse_vendor_result(stdout.decode(errors='strict'))
        result['result']='PASS_WITH_SDK_WARNING' if result['sdk_messages'] else 'PASS'
    except Exception as e:
        result['failure']=str(e)
        if isinstance(e,gate.AdmissionError):result['failed_sample']=e.evidence
    finally:
        if pacer:pacer.close()
        if proc and proc.poll() is None:
            os.killpg(proc.pid,signal.SIGTERM)
            try:proc.wait(timeout=2)
            except subprocess.TimeoutExpired:os.killpg(proc.pid,signal.SIGKILL);proc.wait(timeout=2)
        if proc:
            out,err=proc.communicate(timeout=1);result['child_stdout']=out.decode(errors='replace')[-12000:];result['child_stderr']=err.decode(errors='replace')[-12000:]
        result['units_after']=gate.services();target.write_text(json.dumps(result,indent=2));print(json.dumps(result),flush=True)


if __name__=='__main__':main()
