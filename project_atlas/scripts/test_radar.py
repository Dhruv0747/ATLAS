import serial, time
s = serial.Serial('/dev/ttyAMA0', 256000, timeout=2)
print('Port open, reading 3s...')
time.sleep(0.1)
d = s.read(256)
print('Got', len(d), 'bytes:', d.hex() if d else 'NOTHING')
s.close()
