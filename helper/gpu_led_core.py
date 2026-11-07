#!/usr/bin/env python3
"""Guarded access to an MSI GeForce LED MCU (Blackwell/Ada "MSIv2" style) on Linux.

The controller sits at i2c 7-bit 0x68 on the GPU's internal I2C port 1, which the NVIDIA kernel
driver exposes as a Linux i2c adapter named "NVIDIA i2c adapter 1 at <bdf>". Nothing here uses
NVAPI or OpenRGB: writes go through i2c-dev (i2c-tools) into the driver's own RM I2C path.
"""
import subprocess, os, re, glob, time, datetime

ADDR = 0x68
GPU_VENDOR_DEVICE = (0x10DE, 0x2B85)        # RTX 5090; widen if you add boards
SUBSYSTEM_VENDOR  = 0x1462                  # MSI
REG_ALLOW = {0x2e, 0x46, 0x22, 0x36, 0x38, 0x30, 0x31, 0x32}
REG_FORBIDDEN = {0x3f}                      # APPLY/SAVE: would persist to the card's flash
AUDIT = os.path.expanduser("~/srgb-5090-audit.log")

class NotOurCard(Exception): pass

def find_bus():
    """Return (bus_number, short_bdf) for the adapter that is port 1 of our MSI GPU."""
    for dev in glob.glob("/sys/bus/pci/devices/*"):
        bdf = os.path.basename(dev)                       # 0000:01:00.0
        try:
            ven = int(open(dev + "/vendor").read(), 16); dev_id = int(open(dev + "/device").read(), 16)
            sub = open(dev + "/subsystem_device").read().strip()
        except OSError:
            continue
        if (ven, dev_id) != GPU_VENDOR_DEVICE: continue
        if int(sub, 16) != 0x5300: continue                # MSI Suprim Liquid SOC; widen as needed
        short = bdf[5:]                                    # "01:00.0"
        # the adapter name uses a zero-stripped bus id, e.g. "NVIDIA i2c adapter 1 at 1:00.0"
        forms = {short, "%d:%s" % (int(short.split(":")[0], 16), ":".join(short.split(":")[1:]))}
        for n in glob.glob("/sys/bus/i2c/devices/i2c-*"):
            name = open(n + "/name").read().strip()
            m = re.match(r"NVIDIA i2c adapter (\d+) at (.+)$", name)
            if m and int(m.group(1)) == 1 and m.group(2).strip() in forms:
                return os.path.basename(n).replace("i2c-", ""), m.group(2).strip()
    raise NotOurCard("no MSI GPU I2C port 1 adapter found")

BUS, BDF = None, None

def gate():
    """Re-verify before EVERY transaction: right bus, right chip identity."""
    global BUS, BDF
    if BUS is None:
        BUS, BDF = find_bus()
    name = open(f"/sys/bus/i2c/devices/i2c-{BUS}/name").read().strip()
    if name != f"NVIDIA i2c adapter 1 at {BDF}":
        raise NotOurCard(f"bus {BUS} is now named {name!r}")
    if rd(0xEC) != "0xa1" or rd(0xED) != "0x82":
        raise NotOurCard("LED MCU identity bytes did not match (0xEC/0xED)")
    return True

def rd(reg):
    p = subprocess.run(["i2cget", "-y", str(BUS), hex(ADDR), hex(reg)], capture_output=True, text=True, timeout=20)
    return p.stdout.strip() or "ERR"

def wr(reg, val, tag=""):
    if reg in REG_FORBIDDEN or reg not in REG_ALLOW:
        raise PermissionError(f"register {hex(reg)} is not on the allowlist")
    gate()
    subprocess.run(["i2cset", "-y", str(BUS), hex(ADDR), hex(reg), hex(val), "b"],
                   check=True, capture_output=True, timeout=20)
    with open(AUDIT, "a") as fh:
        fh.write(f"{datetime.datetime.now().isoformat(timespec='milliseconds')} bus={BUS} addr={hex(ADDR)} "
                 f"reg={hex(reg)} val={hex(val)} mode=byte-data{(' tag=' + tag) if tag else ''}\n")
    time.sleep(0.022)

def init_card(brightness=100, speed=0, mode=0x13):
    for reg, val in [(0x2e, 0x00), (0x46, 0x01), (0x22, mode),
                     (0x36, max(0, min(100, brightness))), (0x38, speed)]:
        wr(reg, val, tag="init")

def set_static(r, g, b, mode=0x13, tag=""):
    """The mode byte MUST immediately precede the colour bytes or the chip ignores the colour."""
    wr(0x22, mode, tag=tag)
    for reg, val in [(0x30, r), (0x31, g), (0x32, b)]:
        wr(reg, val, tag=tag)
