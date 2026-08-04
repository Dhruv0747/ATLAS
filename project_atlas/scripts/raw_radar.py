import serial, struct, time
s = serial.Serial('/dev/ttyAMA0', 256000, timeout=0, rtscts=False, dsrdtr=False)
time.sleep(0.5)
buf = b''
HEADER = b'\xaa\xff\x03\x00'
FRAME_LEN = 30
print('Watching radar (Ctrl+C to stop)...', flush=True)
while True:
    chunk = s.read(128)
    if chunk:
        buf += chunk
    else:
        time.sleep(0.005)
        continue
    while len(buf) >= FRAME_LEN:
        idx = buf.find(HEADER)
        if idx < 0:
            buf = b''; break
        if idx > 0:
            buf = buf[idx:]
        if len(buf) < FRAME_LEN: break
        f = buf[:FRAME_LEN]
        buf = buf[FRAME_LEN:]
        if f[-2:] != b'\x55\xcc':
            buf = f[1:] + buf; continue
        x,y,spd,_ = struct.unpack_from('<hHhH', f, 8)
        x2,y2,spd2,_ = struct.unpack_from('<hHhH', f, 16)
        x3,y3 = struct.unpack_from('<hH', f, 24)
        print(f'T1:x={x},y={y},spd={spd}  T2:x={x2},y={y2}  T3:x={x3},y={y3}', flush=True)
