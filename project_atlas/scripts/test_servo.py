#!/usr/bin/env python3
import smbus2, time, sys
I2C_BUS=1; PCA_ADDR=0x42; FREQ_HZ=50
CENTER_US=1500; RANGE_US=400
CHANNEL=int(sys.argv[1]) if len(sys.argv)>1 else 1
MODE1=0x00; PRESCALE=0xFE; CH0_ON_L=0x06
def set_pwm(bus,ch,on,off):
    b=CH0_ON_L+4*ch
    bus.write_byte_data(PCA_ADDR,b,on&0xFF)
    bus.write_byte_data(PCA_ADDR,b+1,on>>8)
    bus.write_byte_data(PCA_ADDR,b+2,off&0xFF)
    bus.write_byte_data(PCA_ADDR,b+3,off>>8)
def us_to_ticks(us): return round(4096*us/(1000000/FREQ_HZ))
def move(bus,us):
    t=us_to_ticks(us); set_pwm(bus,CHANNEL,0,t)
    print(f"  ch{CHANNEL}: {us}us = {t} ticks")
bus=smbus2.SMBus(I2C_BUS)
bus.write_byte_data(PCA_ADDR,MODE1,0x10)
pre=round(25000000/(4096*FREQ_HZ))-1
bus.write_byte_data(PCA_ADDR,PRESCALE,pre)
bus.write_byte_data(PCA_ADDR,MODE1,0x00)
time.sleep(0.005)
bus.write_byte_data(PCA_ADDR,MODE1,0xA0)
print(f"PCA9685 OK ch{CHANNEL} prescale={pre}")
try:
    print("CENTER"); move(bus,CENTER_US); time.sleep(1.0)
    print("LEFT");   move(bus,CENTER_US+RANGE_US); time.sleep(1.5)
    print("CENTER"); move(bus,CENTER_US); time.sleep(1.0)
    print("RIGHT");  move(bus,CENTER_US-RANGE_US); time.sleep(1.5)
    print("CENTER"); move(bus,CENTER_US)
    print("Done.")
except KeyboardInterrupt:
    move(bus,CENTER_US)
finally:
    bus.close()
