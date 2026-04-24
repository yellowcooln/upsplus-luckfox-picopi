#!/usr/bin/env python3

# ''' Update the status of batteries to IoT platform '''
import os
import time
import smbus2
import requests
from ina219 import INA219,DeviceRangeError
import random

DEVICE_NAME = "LuckFox Pico Pi"
DEVICE_BUSES = (2, 1, 3, 4)
DEVICE_ADDR = 0x17
PROTECT_VOLT = 3700
SAMPLE_TIME = 2
FEED_URL = "https://api.52pi.com/feed"
time.sleep(random.randint(0, 59))


def detect_i2c_bus(addresses=(0x17, 0x40, 0x45), candidates=DEVICE_BUSES):
    bus_override = os.environ.get("UPSPLUS_I2C_BUS", "").strip()
    if bus_override:
        return int(bus_override)

    for bus_num in candidates:
        try:
            bus = smbus2.SMBus(bus_num)
            try:
                for address in addresses:
                    bus.read_byte(address)
            finally:
                bus.close()
            return bus_num
        except Exception:
            continue
    raise RuntimeError(f"Could not find UPS Plus devices on I2C buses: {', '.join(str(bus) for bus in candidates)}")


DEVICE_BUS = detect_i2c_bus()

DATA = dict()

ina_supply = INA219(0.00725, busnum=DEVICE_BUS, address=0x40)
ina_supply.configure()
supply_voltage = ina_supply.voltage()
supply_current = ina_supply.current()
DATA['PiVccVolt'] = supply_voltage
DATA['PiIddAmps'] = supply_current

ina_batt = INA219(0.005, busnum=DEVICE_BUS, address=0x45)
ina_batt.configure()
batt_voltage = ina_batt.voltage()
batt_current = ina_batt.current()
DATA['BatVccVolt'] = batt_voltage
try:
    DATA['BatIddAmps'] = batt_current
except DeviceRangeError:
    DATA['BatIddAmps'] = 16000

bus = smbus2.SMBus(DEVICE_BUS)

aReceiveBuf = []
aReceiveBuf.append(0x00)  

for i in range(1,255):
    aReceiveBuf.append(bus.read_byte_data(DEVICE_ADDR, i))

DATA['McuVccVolt'] = aReceiveBuf[2] << 8 | aReceiveBuf[1]
DATA['BatPinCVolt'] = aReceiveBuf[6] << 8 | aReceiveBuf[5]
DATA['ChargeTypeCVolt'] = aReceiveBuf[8] << 8 | aReceiveBuf[7]
DATA['ChargeMicroVolt'] = aReceiveBuf[10] << 8 | aReceiveBuf[9]

DATA['BatTemperature'] = aReceiveBuf[12] << 8 | aReceiveBuf[11]
DATA['BatFullVolt'] = aReceiveBuf[14] << 8 | aReceiveBuf[13]
DATA['BatEmptyVolt'] = aReceiveBuf[16] << 8 | aReceiveBuf[15]
DATA['BatProtectVolt'] = aReceiveBuf[18] << 8 | aReceiveBuf[17]
DATA['SampleTime'] = aReceiveBuf[22] << 8 | aReceiveBuf[21]
DATA['AutoPowerOn'] = aReceiveBuf[25]

DATA['OnlineTime'] = aReceiveBuf[31] << 24 | aReceiveBuf[30] << 16 | aReceiveBuf[29] << 8 | aReceiveBuf[28]
DATA['FullTime'] = aReceiveBuf[35] << 24 | aReceiveBuf[34] << 16 | aReceiveBuf[33] << 8 | aReceiveBuf[32]
DATA['OneshotTime'] = aReceiveBuf[39] << 24 | aReceiveBuf[38] << 16 | aReceiveBuf[37] << 8 | aReceiveBuf[36]
DATA['Version'] = aReceiveBuf[41] << 8 | aReceiveBuf[40]

DATA['UID0'] = "%08X" % (aReceiveBuf[243] << 24 | aReceiveBuf[242] << 16 | aReceiveBuf[241] << 8 | aReceiveBuf[240])
DATA['UID1'] = "%08X" % (aReceiveBuf[247] << 24 | aReceiveBuf[246] << 16 | aReceiveBuf[245] << 8 | aReceiveBuf[244])
DATA['UID2'] = "%08X" % (aReceiveBuf[251] << 24 | aReceiveBuf[250] << 16 | aReceiveBuf[249] << 8 | aReceiveBuf[248])
DATA['DeviceName'] = DEVICE_NAME

print(DATA)
r = requests.post(FEED_URL, data=DATA)
print(r.text)
