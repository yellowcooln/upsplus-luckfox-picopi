#!/usr/bin/env python3
"""
UPS Plus v5 Prometheus exporter for LuckFox Pico Pi.

- Auto-detects the correct I2C bus for the UPS Plus v5 board.
- Exposes metrics over HTTP for Prometheus and Grafana.
- Uses the same UPS Plus register layout as the original logger/exporter.
"""

import os
import sys
import time

import smbus2
from ina219 import INA219, DeviceRangeError
from prometheus_client import Gauge, start_http_server

DEVICE_NAME = "LuckFox Pico Pi"
DEVICE_BUSES = (2, 1, 3, 4)
SMB_DEVICE_ADDR = 0x17
INA_DEVICE_ADDR = 0x40
INA_BATT_ADDR = 0x45
DELAY = 5
STOP_ON_ERR = 0


def detect_i2c_bus(addresses=(SMB_DEVICE_ADDR, INA_DEVICE_ADDR, INA_BATT_ADDR), candidates=DEVICE_BUSES):
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

    raise RuntimeError(
        "Could not find UPS Plus devices on I2C buses: "
        + ", ".join(str(bus_num) for bus_num in candidates)
    )


I2C_DEVICE_BUS = detect_i2c_bus()
bus = smbus2.SMBus(I2C_DEVICE_BUS)
ina = INA219(0.00725, busnum=I2C_DEVICE_BUS, address=INA_DEVICE_ADDR)
ina.configure()
ina_batteries = INA219(0.005, busnum=I2C_DEVICE_BUS, address=INA_BATT_ADDR)
ina_batteries.configure()

UPS_VOLTAGE_MV = Gauge("upsplus_voltage_mv", "Battery voltage from UPS Plus v5 in millivolts")
UPS_POWER_MW = Gauge("upsplus_power_mw", f"{DEVICE_NAME} power draw measured by UPS Plus v5 in milliwatts")
UPS_REMAINING_PERCENT = Gauge("upsplus_remaining_percent", "Remaining battery percentage reported by UPS Plus v5")
UPS_BATT_CURRENT_MA = Gauge(
    "upsplus_battery_current_ma",
    "Battery current from UPS Plus v5 in milliamps (positive = discharge, negative = charge)",
)
UPS_BATT_TEMP_C = Gauge("upsplus_battery_temp_celsius", "Battery temperature reported by UPS Plus v5 in degrees Celsius")
UPS_TIME_SECONDS = Gauge(
    "upsplus_time_seconds",
    "Time value (seconds) provided by UPS Plus v5 (board register, not necessarily Unix time)",
)


def read_values():
    a_receive_buf = [0x00]

    for i in range(1, 255):
        a_receive_buf.append(bus.read_byte_data(SMB_DEVICE_ADDR, i))

    time_s = (
        (a_receive_buf[39] << 24)
        | (a_receive_buf[38] << 16)
        | (a_receive_buf[37] << 8)
        | a_receive_buf[36]
    )
    volts_mv = (a_receive_buf[6] << 8) | a_receive_buf[5]
    remaining_pct = (a_receive_buf[20] << 8) | a_receive_buf[19]
    batt_temp_c = (a_receive_buf[12] << 8) | a_receive_buf[11]

    try:
        power_mw = ina.power()
    except DeviceRangeError:
        power_mw = float("nan")

    try:
        batt_current_ma = ina_batteries.current()
    except DeviceRangeError:
        batt_current_ma = float("nan")

    return {
        "time_s": float(time_s),
        "volts_mv": float(volts_mv),
        "remaining_pct": float(remaining_pct),
        "batt_temp_c": float(batt_temp_c),
        "power_mw": float(power_mw),
        "batt_current_ma": float(batt_current_ma),
    }


def update_metrics():
    values = read_values()

    UPS_TIME_SECONDS.set(values["time_s"])
    UPS_VOLTAGE_MV.set(values["volts_mv"])
    UPS_POWER_MW.set(values["power_mw"])
    UPS_REMAINING_PERCENT.set(values["remaining_pct"])
    UPS_BATT_CURRENT_MA.set(values["batt_current_ma"])
    UPS_BATT_TEMP_C.set(values["batt_temp_c"])

    print(
        f'{DEVICE_NAME}: '
        f'time={values["time_s"]:.0f}s '
        f'voltage={values["volts_mv"]:.0f}mV '
        f'power={values["power_mw"]:.0f}mW '
        f'remaining={values["remaining_pct"]:.0f}% '
        f'batt_current={values["batt_current_ma"]:.0f}mA '
        f'batt_temp={values["batt_temp_c"]:.0f}C'
    )


def main():
    port = int(os.environ.get("UPSPLUS_EXPORTER_PORT", "9105"))
    if len(sys.argv) > 1:
        try:
            port = int(sys.argv[1])
        except ValueError:
            print(f"Invalid port '{sys.argv[1]}', using default {port}")

    print(
        f"Starting UPS Plus v5 Prometheus exporter for {DEVICE_NAME} "
        f"on I2C bus {I2C_DEVICE_BUS}, port {port} ..."
    )
    start_http_server(port)

    while True:
        try:
            update_metrics()
            time.sleep(DELAY)
        except KeyboardInterrupt:
            print("Exiting on Ctrl+C")
            sys.exit(0)
        except Exception as exc:
            print("Unexpected error:", exc)
            if STOP_ON_ERR == 1:
                raise
            time.sleep(DELAY)


if __name__ == "__main__":
    main()
