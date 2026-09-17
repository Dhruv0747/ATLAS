"""Read-only serial fingerprint. No device configuration or transmit commands."""
import collections
import json
import subprocess
import time
import serial
for port in ('/dev/ttyUSB1',):
    if subprocess.run(['fuser',port],capture_output=True).returncode==0:
        print(json.dumps({'port':port,'skip':'busy'}),flush=True)
        continue
    for baud in (9600,115200):
        try:
            link=serial.Serial(port=None,baudrate=baud,timeout=.2,exclusive=True)
            link.dtr=False
            link.rts=False
            link.port=port
            link.open()
            data=bytearray()
            end=time.monotonic()+4
            while time.monotonic()<end:
                data.extend(link.read(4096))
            link.close()
            frames=collections.Counter()
            examples={}
            for i in range(len(data)-10):
                packet=data[i:i+11]
                if packet[0]==0x55 and sum(packet[:10])%256==packet[10]:
                    key=hex(packet[1]);frames[key]+=1;examples[key]=packet.hex()
            sentences=[]
            for line in data.decode('ascii',errors='ignore').splitlines():
                start=line.find('$')
                if start>=0 and '*' in line[start:]:
                    sentence=line[start:]; body,check=sentence[1:].split('*',1)
                    checksum=0
                    for c in body:checksum^=ord(c)
                    try:
                        if checksum==int(check[:2],16):sentences.append(sentence)
                    except ValueError:pass
            print(json.dumps({'port':port,'baud':baud,'bytes':len(data),'valid_imu_frames':dict(frames),'frame_examples':examples,'valid_nmea_count':len(sentences),'nmea_examples':sentences[:6]}),flush=True)
            if frames or sentences:break
        except Exception as exc:
            print(json.dumps({'port':port,'baud':baud,'error':str(exc)}),flush=True)
