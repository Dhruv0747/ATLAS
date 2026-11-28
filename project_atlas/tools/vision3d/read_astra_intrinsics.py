"""One read-only OpenNI factory-parameter query; no streams or property writes."""
import ctypes as C
import json
import math
from pathlib import Path
import sys

ROOT=Path('/home/jetson/project-atlas-migration/astra-20261021')


class CameraParams(C.Structure):
    _fields_=[('left',C.c_float*4),('right',C.c_float*4),('rotation',C.c_float*9),
              ('translation',C.c_float*3),('left_distortion',C.c_float*5),('right_distortion',C.c_float*5)]


def valid_intrinsics(values):
    return len(values)==4 and all(math.isfinite(x) for x in values) and 0<values[0]<10000 and 0<values[1]<10000 and 0<=values[2]<640 and 0<=values[3]<480


def main():
    import depth_stationary_smoke as D
    if C.sizeof(CameraParams)!=120:raise RuntimeError('factory parameter ABI mismatch')
    sdk=C.CDLL(str(ROOT/'astra-arm64-stage29-v2/lib/libOpenNI2.so'))
    ptr=C.c_void_p;listing=C.POINTER(D.DeviceInfo)();count=C.c_int();device=ptr();initialized=False
    def bind(name,args,ret=C.c_int):
        f=getattr(sdk,name);f.argtypes=args;f.restype=ret;return f
    bind('oniInitialize',[C.c_int]);bind('oniShutdown',[],None)
    bind('oniGetDeviceList',[C.POINTER(C.POINTER(D.DeviceInfo)),C.POINTER(C.c_int)])
    bind('oniReleaseDeviceList',[C.POINTER(D.DeviceInfo)])
    bind('oniDeviceOpen',[C.c_char_p,C.POINTER(ptr)]);bind('oniDeviceClose',[ptr])
    bind('oniDeviceGetProperty',[ptr,C.c_int,ptr,C.POINTER(C.c_int)])
    bind('oniSetLogFileOutput',[C.c_int]);bind('oniSetLogConsoleOutput',[C.c_int])
    result={'query':'READ ONLY OBEXTENSION_ID_CAM_PARAMS=14','streams_started':False}
    try:
        sdk.oniSetLogFileOutput(0);sdk.oniSetLogConsoleOutput(0)
        if sdk.oniInitialize(2003)!=0:raise RuntimeError('OpenNI init failed')
        initialized=True
        if sdk.oniGetDeviceList(C.byref(listing),C.byref(count))!=0 or not 0<count.value<=16:raise RuntimeError('enumeration failed')
        found=[listing[i] for i in range(count.value) if (listing[i].usbVendorId,listing[i].usbProductId)==(0x2bc5,0x0403)]
        if len(found)!=1 or sdk.oniDeviceOpen(found[0].uri,C.byref(device))!=0:raise RuntimeError('exact Astra open failed')
        params=CameraParams();size=C.c_int(C.sizeof(params))
        rc=sdk.oniDeviceGetProperty(device,14,C.byref(params),C.byref(size))
        result.update(status=rc,returned_bytes=size.value,
                      fields={k:[float(x) if math.isfinite(x) else None for x in getattr(params,k)] for k,_ in params._fields_},
                      valid_factory_intrinsics=rc==0 and size.value==120 and valid_intrinsics(list(params.left)) and valid_intrinsics(list(params.right)))
    finally:
        if device:sdk.oniDeviceClose(device)
        if listing:sdk.oniReleaseDeviceList(listing)
        if initialized:sdk.oniShutdown()
    print('ATLAS_INTRINSICS_RESULT '+json.dumps(result,allow_nan=False),flush=True)


if __name__=='__main__':main()
