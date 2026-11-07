# Upstream notes

Two things would make this helper unnecessary:

1. **Linux I2C bus enumeration.** If the engine's Linux `I2CBusManager` also enumerated adapters named
   `NVIDIA i2c adapter %hu at %04x:%02x:%02x.%u`, attached the owning PCI ids + port number, implemented
   `IsNvidiaBus()` on that basis, and routed the NVAPI-gated `WriteByte`/`WriteBlock`/`ReadByte` through
   `I2C_SLAVE` + `I2C_SMBUS`, then the existing `MSI_GPU.js` / ASUS / EVGA / Gigabyte GPU plugins would
   work unmodified on Linux. `NvAPI_I2CRead`/`NvAPI_I2CWrite` are NULL in NVIDIA's Linux NVAPI shim, so
   the NVAPI requirement cannot be met there.

2. **This SKU's support level.** `0x5300` (RTX 5090 Suprim Liquid SOC) is currently only in the legacy
   single-zone `MSI_GPU.js`; it was removed from `MSI_GPU_Blackwell.js` in commit `747083d4`
   ("Reverting Suprim Liquid, no testers found"). The tester problem is solvable: owners exist, and the
   sequence in `README.md` is confirmed working on real hardware on Linux.

Gotchas measured on hardware that are worth putting in whichever engine path implements this:
- the mode register (`0x22`) must be re-written immediately before the colour registers on every update;
  colour-only writes are acknowledged by the chip but not applied;
- colour/mode registers do not read back truthfully - only `0xEC`/`0xED` are reliable reads;
- `0x3F` is `APPLY` in SignalRGB's table and `SAVE` in OpenRGB's - treat persistence as a separate,
  explicit action rather than a side effect of setting a colour.

OpenRGB already registers these boards on Linux over the same adapters
(`MSIGPUv2ControllerDetect.cpp`, address `0x68`, `port_id == 1`), so the address map is corroborated.
