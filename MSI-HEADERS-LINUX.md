# MSI motherboard ARGB headers dead on SignalRGB for Linux - cause and one-line fix

**Board:** MSI MAG X870E TOMAHAWK WIFI (MS-7E59), Mystic Light USB controller `0db0:0076`
**App:** SignalRGB for Linux 2.5.85-7583 (beta .deb). Same board + plugin works on Windows.

## Cause
`Plugins/Msi/185 Byte Motherboard Controller/MSI_185Byte_Controller_0x0DB0.js` aborts if it cannot read a
BIOS version:

```js
if(!biosInfo) {
    device.notify("Failed to fetch bios version from WMI!", "...", 1);
    Assert.fail("Failed to fetch bios version from WMI after 10 attempts!");
    return;
}
compareBiosVersion(biosInfo, motherboardName);
```

`Assert.fail()` aborts `Initialize()` before `initializeMotherboard()`, so the headers are never
registered - and nothing after that point needs the BIOS version except `compareBiosVersion()`.

Why `biosInfo` is always empty on Linux: `SystemInfo::GetMotherboardInfo()` **is** implemented there - it
reads `/sys/class/dmi/id/product_name` and `/sys/class/dmi/id/sys_vendor`, which is why the board-name
lookup and the `Library` / `ConfigurationOverrides[motherboardName]` layout selection work fine. But the
binary contains no read of `/sys/class/dmi/id/bios_version` or `bios_date`, so `SystemInfo::GetBiosInfo()`
has nothing to return and the assert fires on every start.

## Try it without touching your install
Copy the plugin to the user plugin directory and apply the patch there:

```bash
mkdir -p ~/Documents/WhirlwindFX/Plugins
cp ~/.cache/WhirlwindFX/SignalRgb/plugin_cdn/dev/Plugins/Msi/\
   '185 Byte Motherboard Controller/MSI_185Byte_Controller_0x0DB0.js' \
   ~/Documents/WhirlwindFX/Plugins/
cd ~/Documents/WhirlwindFX/Plugins && patch -p3 < msi-wmi-assert.patch   # adjust -p as needed
```
The user plugin directory overrides the CDN copy, and removing the file reverts.
Restart SignalRGB: the board should enumerate and the headers follow effects.

## Important caveat for anyone copying this
Do **not** remove the *motherboard name* assert as well. `motherboardName` comes from
`GetMotherboardInfo()` (which works on Linux) and is the key into the header-layout tables - nulling that
path breaks board selection. Only the BIOS-version gate needs softening.

And note the file's own warning: `YOU CAN BRICK THESE MOTHERBOARDS RGB CONTROLLER WITH ONE WRONG PACKET`.
This change touches no packet code; that is deliberate.

## Upstream
Committed as a branch + patch here (`msi-wmi-assert.patch`) and offered as a merge request to
`gitlab.com/signalrgb/signal-plugins`. It would also fit their `signalrgb/hotfix` add-on, which exists to
ship plugin fixes between releases. A better long-term fix is engine-side: implement `GetBiosInfo()` on
Linux from `/sys/class/dmi/id/bios_version` (with a graceful empty result), which makes the whole class of
"WMI-backed call in a plugin init path" failure go away. Other motherboard plugins may assume the same.
