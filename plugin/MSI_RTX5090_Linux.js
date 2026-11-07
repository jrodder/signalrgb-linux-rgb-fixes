export function Name() { return "MSI RTX 5090 Suprim Liquid (Linux)"; }
export function Version() { return "0.1.0"; }
export function Type() { return "network"; }
export function Publisher() { return "local"; }
export function Size() { return [1, 1]; }
export function DefaultPosition() { return [10, 10]; }
export function DefaultScale() { return 0.12; }
export function Documentation() { return "https://docs.signalrgb.com/"; }

export function ControllableParameters() {
  return [
    {"property":"hwBrightness","label":"Hardware Brightness","type":"number","min":"1","max":"100","step":"1","default":"100"}
  ];
}

/* global
controller:readonly
*/

const HOST = "127.0.0.1";
const PORT = 50910;
const MAGIC = [0x53, 0x47, 0x42, 0x31];   // "SGB1" - the local helper checks this

let lastSent = [0, 0, 0];
let lastStamp = 0;

export function Initialize() {
  device.setName(controller.name);
  device.addFeature("udp");
}

function send(r, g, b, apply) {
  const bright = Math.max(0, Math.min(100, parseInt(hwBrightness, 10) || 100));
  udp.send(HOST, PORT, MAGIC.concat([r & 0xff, g & 0xff, b & 0xff, bright, apply ? 1 : 0]));
}

export function Render() {
  const now = Date.now();
  if (now - lastStamp < 50) { return; }          // cap the bus at ~20 update groups/s

  const c = device.color(0, 0);
  const r = c[0] | 0, g = c[1] | 0, b = c[2] | 0;
  if (r === lastSent[0] && g === lastSent[1] && b === lastSent[2] && now - lastStamp < 2000) { return; }

  lastSent = [r, g, b];
  lastStamp = now;
  send(r, g, b, true);
}

export function Shutdown() {
  send(0, 0, 0, false);
}

export function DiscoveryService() {
  this.IconUrl = "https://assets.signalrgb.com/brands/msi/logo.png";

  this.Initialize = function () { };

  this.Update = function () {
    if (service.getController("msi5090linux0") !== undefined) { return; }
    const cont = new GpuController();
    service.addController(cont);
    service.announceController(cont);
  };

  this.Discovered = function (value) { };
}

class GpuController {
  constructor() {
    this.id = "msi5090linux0";
    this.name = "MSI RTX 5090 Suprim Liquid SOC";
    this.ip = "127.0.0.1";
    service.log("Local GPU LED controller constructed");
  }

  updateWithValue(value) {
    if (value) {
      this.id = value.id || this.id;
      this.name = value.name || this.name;
    }
  }

  update() { }
  turnOn() { }
  turnOff() { }
  startLink() { }
  startRemove() { }
  startDelete() { }
}
