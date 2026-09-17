"""30-second IM10A/WIT serial baseline. No serial writes or ROS publications."""
import collections
import json
import math
import statistics
import struct
import subprocess
import time
import serial

port='/dev/serial/by-path/platform-3610000.usb-usb-0:2.2.4.1:1.0-port0'
if subprocess.run(['fuser',port],capture_output=True).returncode==0:
    raise SystemExit('Port busy; no probe performed')
link=serial.Serial(port=None,baudrate=9600,timeout=.05,exclusive=True)
link.dtr=False
link.rts=False
link.port=port
link.open()
rows=collections.defaultdict(list)
bad=0
discarded=0
buffer=bytearray()
started=time.monotonic()
try:
    while time.monotonic()-started<30:
        buffer.extend(link.read(max(1,min(link.in_waiting,4096))))
        while len(buffer)>=11:
            if buffer[0]!=0x55:
                del buffer[0];discarded+=1;continue
            packet=bytes(buffer[:11])
            if sum(packet[:10])%256!=packet[10]:
                bad+=1;del buffer[0];continue
            del buffer[:11]
            rows[packet[1]].append((time.monotonic(),struct.unpack('<4h',packet[2:10])))
finally:
    link.close()
out={'duration_s':time.monotonic()-started,'checksum_failures':bad,'discarded_bytes':discarded,
     'scaling':'WIT standard packet scales: accel 16g, gyro 2000deg/s, Euler 180deg; magnetic values native raw, not tesla','streams':{}}
for kind,samples in rows.items():
    scale={0x51:16/32768,0x52:2000/32768,0x53:180/32768,0x59:1/32768}.get(kind,1)
    count=4 if kind==0x59 else 3
    values=[tuple(v*scale for v in s[1][:count]) for s in samples]
    summary={'count':len(samples),'unique':len(set(values)),'rate_hz':len(samples)/out['duration_s']}
    if len(samples)>1:summary['max_gap_s']=max(b[0]-a[0] for a,b in zip(samples,samples[1:]))
    summary['axes']=[{'mean':statistics.mean(v),'min':min(v),'max':max(v),'std':statistics.pstdev(v)} for v in zip(*values)]
    if kind==0x51:summary['acceleration_norm_g_mean']=statistics.mean(math.sqrt(sum(x*x for x in v)) for v in values)
    if kind==0x53:summary['yaw_end_minus_start_deg']=(values[-1][2]-values[0][2]+180)%360-180
    if kind==0x59:summary['quaternion_norm_mean']=statistics.mean(math.sqrt(sum(x*x for x in v)) for v in values)
    out['streams'][hex(kind)]=summary
print(json.dumps(out,indent=2))
