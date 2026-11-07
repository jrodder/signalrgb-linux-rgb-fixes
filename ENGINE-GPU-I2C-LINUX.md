# [Linux] GPU RGB is unreachable: the Linux `I2CBusManager` never registers the GPU's I2C adapters, and GPU plugins hard-gate on NVAPI, which has no I2C on Linux

**Component:** SignalRGB engine, Linux I2C bus enumeration + GPU plugin bus selection
**Version:** SignalRGB for Linux 2.5.85-7583 (beta .deb)
**Hardware:** MSI GeForce RTX 5090 SUPRIM LIQUID SOC (`10de:2b85`, subsystem `1462:5300`), driver 615.71.09
**Result:** the card is detected (`Found GPU NVIDIA GB202 [GeForce RTX 5090] [10DE:2B85]`) but no lighting
device is ever created. Same card + same plugin works on Windows.

## What happens
1. On Linux the engine only creates buses for a **chipset SMBus controller**. Binary strings:
   `i2c-piix4`, `Found %1 i2c adapters but no SMBus controller among them.`,
   `Created Linux I2C bus at %1, with Vendor: %2, Device: %3`. On this machine that yields
   `Found 3 I2C buses` (the AMD PIIX4 ports) and nothing else.
2. GPU plugins gate on the bus they are handed, e.g. `MSI_GPU_Blackwell.js` / `MSI_GPU.js`:
   ```js
   if (!bus.IsNvidiaBus()) { return []; }
   ```
   On Linux no bus can ever satisfy `IsNvidiaBus()`, so the scan returns nothing.
3. The remaining GPU I/O paths are NVAPI-gated (`no Write Block Bytes outside of NvApi`).

## Why the NVAPI gate cannot be satisfied on Linux
Measured on this box, `libnvidia-api.so.1` (615.71.09) exports only `nvapi_QueryInterface`; resolving the
I2C entry points returns NULL:

| entry point | id | result |
|---|---|---|
| `NvAPI_I2CRead` | `0x2FDE12C5` | NULL |
| `NvAPI_I2CWrite` | `0xE812EB07` | NULL |
| `NvAPI_I2CReadEx` / `WriteEx` | undocumented | NULL |
| `NvAPI_GPU_ClientIllumZonesGetControl` | `0x3DBF5764` | present |

So the Illumination calls exist and the I2C transport does not. Requiring NVAPI makes GPU RGB
structurally impossible on Linux.

## But the transport already exists on Linux — your driver creates it
The NVIDIA kernel module registers one Linux I2C adapter **per GPU I2C port**, not per display output, and
routes every transfer from those adapters into the same RM I2C machinery NVAPI uses on Windows:

```
$ cat /sys/bus/i2c/devices/i2c-4/name
NVIDIA i2c adapter 1 at 1:00.0

# nv-i2c.c: both nv_i2c_algo_master_xfer() and nv_i2c_algo_smbus_xfer() call rm_i2c_transfer()
# which services RM class NV40_I2C (0x0000402C), control 0x402c0105 - non-privileged
```
Port 1 is the internal/communications port where AIB RGB controllers live — OpenRGB's NVAPI backend says
so in a comment: *"Always use GPU port 1 - this is where RGB controllers are attached"*.

**The LED controller is sitting on a bus Linux can already address.** Read-only probe on this card:

```
$ i2cget -y 4 0x68 0xec b   -> 0xa1
$ i2cget -y 4 0x68 0xed b   -> 0x82        # 0x82xx = the MSI LED MCU id documented for Suprim boards
$ i2cdetect -y -r 4         -> exactly one device answers: 0x68
```

## It is not just theoretical: we drove the card on Linux
Replaying your own `MSI_GPU.js` `is50SeriesCard` byte sequence over `i2c-dev` (SMBus byte data) lit the
card and it then tracked a live SignalRGB effect. Sequence, in order, at slave `0x68`:

```
0x2E <- 0x00      init
0x46 <- 0x01      50-series flag
0x22 <- 0x13      mode = STATIC
0x36 <- 0x64      brightness (percent, passed straight through)
0x38 <- 0x00      effect speed ("Yay 50 series quirks")
0x30/0x31/0x32 <- R,G,B
```
Two findings that may help whoever implements this:
- The **mode byte must be re-written immediately before the colour bytes on every update**. Colour-only
  writes are acknowledged by the chip but the LEDs do not change. (One reason a naive port would look
  broken even when the transport works.)
- Colour/mode registers do not read back truthfully on this MCU; only `0xEC`/`0xED` are reliable reads.
- `0x3F` (your table: `APPLY`, OpenRGB: `SAVE`) was never written; nothing we did persisted to flash.

To be clear about scope: your plugin's support for this SKU currently lives in the legacy single-zone
file (commit `747083d4` "Reverting Suprim Liquid, no testers found" removed it from the Blackwell plugin),
so this is about single-zone colour, which is what your Windows support for the card provides today.

## Requested change (small)
In the Linux `I2CBusManager`, also enumerate kernel adapters whose name matches
`"NVIDIA i2c adapter %hu at %04x:%02x:%02x.%u"`, attach the owning PCI vendor/device/subsystem ids and the
port number to the bus object, implement `IsNvidiaBus()` as "the owning PCI device is an NVIDIA display
class device" plus `Port`, and route the currently NVAPI-gated `WriteByte`/`WriteBlock`/`ReadByte` paths
through `I2C_SLAVE` + `I2C_SMBUS` for those buses. **No plugin changes needed** — the MSI/ASUS/EVGA/Gigabyte
GPU plugins already do `if (!bus.IsNvidiaBus()) return [];` and then plain register writes, and the address
(`0x68` for MSI) already matches what OpenRGB registers for the same boards.

## Prior art on Linux, same adapters
OpenRGB (`i2c_smbus_linux.cpp` scans for the same adapter-name pattern; registers MSI GeForce boards at
`0x68` guarded on `port_id == 1`), liquidctl (requires `NVIDIA i2c adapter 1 `), and gpulux (raw
`I2C_RDWR` on MSI cards). So the approach is demonstrated by three shipped tools.

## Notes on safety
This was read-mostly investigation; the only writes were to `0x68`, volatile (no save/apply byte), with a
register allowlist, and the user owns this machine and approved them. No damage report of a GPU LED
controller being harmed by these writes was found in OpenRGB issues, forums or Reddit. Recovery for that
MCU class is a cold power cycle.

Happy to test a Linux build with this enabled, and to provide the plugin + helper we used.
