from smbus2 import SMBus
import time
A = 0x68
b = SMBus(1)
b.write_byte_data(A, 0x6B, 0)      # wake up
b.write_byte_data(A, 0x1B, 0x08)   # gyro range +-500 deg/s
while True:
    d = b.read_i2c_block_data(A, 0x43, 6)
    v = [((d[i] << 8) | d[i+1]) for i in (0, 2, 4)]
    v = [(x - 65536 if x > 32767 else x) / 65.5 for x in v]
    print("gx %7.1f  gy %7.1f  gz %7.1f deg/s" % tuple(v))
    time.sleep(0.2)
