# MSI RTX 5090 Suprim Liquid RGB on Linux, driven by SignalRGB

Lights the SOC LEDs of an **MSI GeForce RTX 5090 SUPRIM LIQUID SOC** (`10de:2b85`,
subsystem `1462:5300`) on **SignalRGB for Linux**, with no OpenRGB and no NVAPI.

Verified working on SignalRGB 2.5.85-7583 (Linux beta), NVIDIA driver 615.71.09, Ubuntu.
The card follows whatever effect you put on the device in SignalRGB.

## Why this exists
SignalRGB's Linux build only creates I2C buses for a chipset SMBus controller, so a GPU plugin's
`if (!bus.IsNvidiaBus()) return [];` can never succeed, and the NVAPI-gated GPU I/O paths do not exist
on Linux (`NvAPI_I2CRead`/`Write` resolve to NULL in `libnvidia-api.so.1`). The LED controller itself is
reachable: the NVIDIA driver exposes each GPU I2C **port** as a Linux adapter, and port 1 is where the
AIB RGB chip lives (`NVIDIA i2c adapter 1 at 0000:01:00.0`, controller at `0x68`).

So this is a user plugin plus a small local helper, using SignalRGB's own byte sequence from
`Plugins/Msi/GPU's/MSI_GPU.js` (`is50SeriesCard` branch). Upstream fix proposal in
`UPSTREAM.md`.

## Install
```bash
# 1. plugin (SignalRGB's user plugin directory - no add-on install needed)
mkdir -p ~/Documents/WhirlwindFX/Plugins
cp plugin/MSI_RTX5090_Linux.js ~/Documents/WhirlwindFX/Plugins/

# 2. helper
mkdir -p ~/bin && cp helper/gpu_led_core.py helper/gpu-led-bridge helper/gpu-led ~/bin/
chmod +x ~/bin/gpu-led-bridge ~/bin/gpu-led
sudo usermod -aG i2c $USER     # then log out/in, so no sudo is needed

# 3. start the helper, then restart SignalRGB
~/bin/gpu-led-bridge &
```
A device named "MSI RTX 5090 Suprim Liquid SOC" appears in SignalRGB (log line:
`Network Services Found: N+1`, `Starting discovery thread for .../MSI_RTX5090_Linux.js`). Put any effect
on it. **Hardware Brightness** is in the device's settings.

## How it works
```
SignalRGB canvas -> MSI_RTX5090_Linux.js (Type "network", 1 LED)
      -> udp.send("SRGB1" R G B brightness apply) to 127.0.0.1:50910
      -> gpu-led-bridge -> i2cset -y <bus> 0x68 <reg> <val> b   (SMBus byte data)
```
Byte sequence, per colour update:

| register | value | note |
|---|---|---|
| `0x2E` | `0x00` | init, once |
| `0x46` | `0x01` | 50-series flag, once |
| `0x36` | brightness % | percent, passed straight through |
| `0x38` | `0x00` | effect speed quirk |
| `0x22` | `0x13` | mode = STATIC - **must immediately precede the colour bytes** |
| `0x30/0x31/0x32` | R, G, B | |

Two things that will bite you if you write your own version:
- Colour-only writes are **acknowledged but ignored**. Re-write `0x22` before `0x30/0x31/0x32` every time.
- Colour and mode registers **do not read back truthfully**. Only `0xEC` (`0xa1`) and `0xED` (`0x82`, the
  high byte of the `0x8232` MSI LED MCU id) are reliable reads - they are used here as the identity gate.

## Safety rails in `gpu_led_core.py`
- bus resolved by adapter name **and** PCI vendor/device/subsystem, re-checked before every transaction
- chip identity registers (`0xEC`/`0xED`) verified before every transaction
- register allowlist; `0x3F` (APPLY/SAVE in SignalRGB/OpenRGB terms) is unreachable, so **nothing here
  survives a reboot** and the card's flash is never worn
- >=22 ms between writes, colour updates capped at ~10/s, change-threshold to skip no-op traffic
- every transaction appended to `~/srgb-5090-audit.log`
- `~/bin/gpu-led set #rrggbb` / `off` / `status` for manual control (do not run while the bridge runs)

## Known scope
Single zone, one colour - which matches SignalRGB's own current support for this SKU (it lives in the
legacy single-zone `MSI_GPU.js`; commit `747083d4` "Reverting Suprim Liquid, no testers found" removed it
from the Blackwell plugin). Per-LED block writes exist only in one place (`0x04`/`0x06`/`0x20` in the
Blackwell plugin) and are unverified, so they are not implemented here.

## Untested for
Other MSI Blackwell/Ada SKUs (widen `find_bus()`/`GPU_VENDOR_DEVICE`), other vendors' addresses
(OpenRGB's detectors list them all on port 1), suspend/resume behaviour, and dual-GPU boxes.

Not affiliated with WhirlwindFX. Trademarks belong to their owners. Add a licence file before publishing
if you care about the terms.
