from __future__ import annotations

import fcntl
from pathlib import Path

I2C_SLAVE = 0x0703
I2C_DEVICE = Path("/dev/i2c-1")
I2C_ADDRESS = 0x36


def read_word(register: int) -> int:
    with I2C_DEVICE.open("r+b", buffering=0) as device:
        fcntl.ioctl(device.fileno(), I2C_SLAVE, I2C_ADDRESS)
        device.write(bytes([register]))
        data = device.read(2)

    if len(data) != 2:
        raise OSError(f"Short I2C read from register 0x{register:02x}")

    return (data[0] << 8) | data[1]


soc_raw = read_word(0x04)
vcell_raw = read_word(0x02)

raw_percent = (soc_raw >> 8) + ((soc_raw & 0xFF) / 256.0)
percent = max(0, min(100, round(raw_percent)))

# MAX17040 VCELL: 12-bit value left-aligned; 1.25 mV per step.
voltage_v = ((vcell_raw >> 4) * 1.25) / 1000.0

print("x1206_battery_available")
print(f"soc_raw=0x{soc_raw:04x}")
print(f"vcell_raw=0x{vcell_raw:04x}")
print(f"raw_percent={raw_percent:.2f}")
print(f"percent={percent}")
print(f"voltage_v={voltage_v:.3f}")
print(f"source={I2C_DEVICE}@0x{I2C_ADDRESS:02x}:MAX17040")
