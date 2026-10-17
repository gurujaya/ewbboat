// Everything in the 3D scene that isn't the boat or particles: sky, water, shore, the ground
// station, fences, the trail, the sweep plan, the coverage grid, trash pins and labels.

import * as THREE from 'three';
import { Sky } from 'three/addons/objects/Sky.js';
import { CSS2DRenderer, CSS2DObject } from 'three/addons/renderers/CSS2DRenderer.js';
import { Line2 } from 'three/addons/lines/Line2.js';
import { LineGeometry } from 'three/addons/lines/LineGeometry.js';
import { LineMaterial } from 'three/addons/lines/LineMaterial.js';
import { createSurface, shoreZ } from './surface.js';
import { createTerrain, heightAt } from './terrain.js';
import { toXZ } from './geo.js';

// ---------------------------------------------------------------------------------------------
// renderer, sky, light
// ---------------------------------------------------------------------------------------------
export function createRenderer(canvas, labelHost) {
  const renderer = new THREE.WebGLRenderer({ canvas, antialias: true, powerPreference: 'high-performance' });
  renderer.setPixelRatio(Math.min(2, devicePixelRatio));
  renderer.toneMapping = THREE.ACESFilmicToneMapping;
  renderer.toneMappingExposure = 0.5;
  const labels = new CSS2DRenderer({ element: labelHost });
  return { renderer, labels };
}

export function createEnvironment(renderer, scene) {
  // dusk: the sun just above the north-west horizon, a deep blue sky, warm light low across the
  // water. Dark enough that the panels float on it; the glint path lies ahead of the camera.
  const sky = new Sky();
  sky.scale.setScalar(6000);
  const u = sky.material.uniforms;
  u.turbidity.value = 6.0;
  u.rayleigh.value = 2.2;
  u.mieCoefficient.value = 0.006;
  u.mieDirectionalG.value = 0.9;
  const sunDir = new THREE.Vector3().setFromSphericalCoords(1, THREE.MathUtils.degToRad(90 - 4), THREE.MathUtils.degToRad(205));
  u.sunPosition.value.copy(sunDir);
  scene.add(sky);

  // a cube map of the sky: the water reflects it, the boat's metal and paint are lit by it
  const cubeRT = new THREE.WebGLCubeRenderTarget(256, { type: THREE.HalfFloatType });
  const cubeCam = new THREE.CubeCamera(1, 10000, cubeRT);
  // capture without the sun disc: it is brighter than a half-float can hold, and one infinite
  // pixel turns every lit surface black. The water draws its own sun glint.
  u.showSunDisc.value = 0;
  cubeCam.update(renderer, scene);
  u.showSunDisc.value = 1;
  const pmrem = new THREE.PMREMGenerator(renderer);
  scene.environment = pmrem.fromCubemap(cubeRT.texture).texture;
  scene.environmentIntensity = 0.7;

  // the fog color is the sky right at the horizon, so the water fades into it with no seam
  // (some GPUs can't read half-float pixels back; then use a color picked by eye)
  const fogColor = new THREE.Color(0.32, 0.34, 0.36);
  try {
    const px = new Uint16Array(4);
    renderer.readRenderTargetPixels(cubeRT, 128, 128, 1, 1, px, 5);   // face 5 looks along -z (north)
    const rgb = [0, 1, 2].map((i) => THREE.DataUtils.fromHalfFloat(px[i]));
    if (rgb.every((v) => Number.isFinite(v)) && rgb.some((v) => v > 0.001)) fogColor.setRGB(...rgb);
  } catch { /* keep the fallback */ }

  const sunColor = new THREE.Color(1.0, 0.72, 0.5);
  const sun = new THREE.DirectionalLight(sunColor, 1.6);
  sun.position.copy(sunDir).multiplyScalar(100);
  scene.add(sun, sun.target);
  scene.add(new THREE.HemisphereLight(0x5f7fa6, 0x141a1c, 0.55));
  scene.fog = new THREE.FogExp2(fogColor, 0.0016);

  // land and water come after the sky capture, so the environment light is pure sky
  createTerrain(scene);
  const surface = createSurface(renderer, { envCube: cubeRT.texture, sky, sunDir, sunColor, fogColor, fogDensity: 0.0016 });
  scene.add(surface);
  return { surface, sky, sunDir, fogColor };
}

// ---------------------------------------------------------------------------------------------
// labels (DOM elements that follow a point in the scene)
// ---------------------------------------------------------------------------------------------
export function label(text, cls = '') {
  const el = document.createElement('div');
  el.className = 'scene-label ' + cls;
  el.textContent = text;
  const obj = new CSS2DObject(el);
  obj.center.set(0.5, 1.15);
  return obj;
}

// ---------------------------------------------------------------------------------------------
// shore furniture: the station, its pad, and a small launch jetty
// ---------------------------------------------------------------------------------------------
export function createStation(scene) {
  const g = new THREE.Group();
  const grey = new THREE.MeshStandardMaterial({ color: 0x9aa1a8, roughness: 0.85 });
  const metal = new THREE.MeshStandardMaterial({ color: 0xc9ced4, metalness: 0.8, roughness: 0.35 });
  const white = new THREE.MeshStandardMaterial({ color: 0xeef1f4, roughness: 0.5 });
  const dark = new THREE.MeshStandardMaterial({ color: 0x2a2f35, roughness: 0.7 });

  const pad = new THREE.Mesh(new THREE.BoxGeometry(2.2, 0.12, 2.2), grey); pad.position.y = 0.06; g.add(pad);
  const pole = new THREE.Mesh(new THREE.CylinderGeometry(0.045, 0.06, 5.2, 16), metal); pole.position.y = 2.72; g.add(pole);
  // weatherproof enclosure for the station Pi, strapped to the pole
  const encl = new THREE.Mesh(new THREE.BoxGeometry(0.42, 0.52, 0.2), white); encl.position.set(0, 1.25, 0.16); g.add(encl);
  const door = new THREE.Mesh(new THREE.BoxGeometry(0.38, 0.48, 0.005), new THREE.MeshStandardMaterial({ color: 0xdfe3e8, roughness: 0.45 }));
  door.position.set(0, 1.25, 0.263); g.add(door);
  // sector antenna aimed north over the water
  const ant = new THREE.Mesh(new THREE.BoxGeometry(0.16, 0.55, 0.06), white); ant.position.set(0, 4.95, -0.12); ant.rotation.x = -0.12; g.add(ant);
  const bracket = new THREE.Mesh(new THREE.BoxGeometry(0.06, 0.08, 0.12), dark); bracket.position.set(0, 4.95, -0.05); g.add(bracket);
  const led = new THREE.Mesh(new THREE.SphereGeometry(0.035, 12, 8), new THREE.MeshBasicMaterial({ color: 0x34d399, toneMapped: false }));
  led.position.set(0.14, 1.42, 0.27); g.add(led);
  // a small warm work light on the mast: at dusk it's how you find the station from the water
  const lamp = new THREE.PointLight(0xffc98a, 6, 14, 1.6); lamp.position.set(0, 4.6, 0.1); g.add(lamp);
  const bulb = new THREE.Mesh(new THREE.SphereGeometry(0.05, 12, 8), new THREE.MeshBasicMaterial({ color: 0xffe2b8, toneMapped: false })); bulb.position.copy(lamp.position); g.add(bulb);
  const lbl = label('Ground station', 'is-station'); lbl.position.set(0, 5.6, 0); g.add(lbl);
  g.position.y = heightAt(0, 0);              // stand on the ground, not at water level
  scene.add(g);

  // jetty: planks on pilings from the shore out into the water, where the boat launches
  const wood = new THREE.MeshStandardMaterial({ color: 0x6b5843, roughness: 0.9 });
  const jx = 3.2, z0 = shoreZ(jx) + 3, z1 = -11;
  const n = Math.floor((z0 - z1) / 0.26);
  const planks = new THREE.InstancedMesh(new THREE.BoxGeometry(1.5, 0.05, 0.22), wood, n);
  const m = new THREE.Matrix4();
  for (let i = 0; i < n; i++) {
    m.makeRotationY((Math.random() - 0.5) * 0.02).setPosition(jx + (Math.random() - 0.5) * 0.02, 0.42, z0 - i * 0.26);
    planks.setMatrixAt(i, m);
  }
  scene.add(planks);
  const piling = new THREE.CylinderGeometry(0.07, 0.07, 1.2, 10);
  for (let z = z0 - 0.4; z > z1; z -= 2.2) for (const dx of [-0.68, 0.68]) {
    const p = new THREE.Mesh(piling, wood); p.position.set(jx + dx, -0.05, z); scene.add(p);
  }
  return { led, antennaTop: new THREE.Vector3(0, 5.0, -0.15) };
}

// ---------------------------------------------------------------------------------------------
// fences: thin dashed lines on the water, like a chart overlay (no glowing walls)
// ---------------------------------------------------------------------------------------------
export const lineMat = (color, width, opts = {}) => new LineMaterial({ color, linewidth: width, transparent: true, depthWrite: false, ...opts });

function fenceLine(pts, color, width, opacity) {
  const line = new Line2(new LineGeometry().setPositions(pts.flatMap(([x, z]) => [x, 0.06, z])), lineMat(color, width, { opacity, dashed: true, dashSize: 2.2, gapSize: 1.4 }));
  line.computeLineDistances();
  line.renderOrder = 3;
  line.userData.dispose = () => line.geometry.dispose();
  return line;
}

export function rectFence(c0, c1, color, width = 1.6, opacity = 0.85) {
  const [x0, z0] = toXZ(c0[0], c0[1]);
  const [x1, z1] = toXZ(c1[0], c1[1]);
  return fenceLine([[x0, z0], [x1, z0], [x1, z1], [x0, z1], [x0, z0]], color, width, opacity);
}

// the driving fence is a circle round the station (boat-pi enforces the same radius)
export function circleFence(radiusM, color, width = 1.4, opacity = 0.6) {
  const pts = [];
  for (let i = 0; i <= 256; i++) { const a = (i / 256) * Math.PI * 2; pts.push([Math.cos(a) * radiusM, Math.sin(a) * radiusM]); }
  return fenceLine(pts, color, width, opacity);
}

// ---------------------------------------------------------------------------------------------
// the trail: a line colored by signal strength, with a dot at every trail point
// ---------------------------------------------------------------------------------------------
const SIGNAL_STOPS = [[-55, 0x34d399], [-70, 0xfacc15], [-80, 0xfb923c], [-88, 0xef4444]];
export function signalColor(dbm, out = new THREE.Color()) {
  if (dbm == null) return out.set(0xef4444);
  if (dbm >= SIGNAL_STOPS[0][0]) return out.set(SIGNAL_STOPS[0][1]);
  for (let i = 1; i < SIGNAL_STOPS.length; i++) {
    const [d1, c1] = SIGNAL_STOPS[i], [d0, c0] = SIGNAL_STOPS[i - 1];
    if (dbm >= d1) return out.set(c0).lerp(_c.set(c1), (d0 - dbm) / (d0 - d1));
  }
  return out.set(SIGNAL_STOPS.at(-1)[1]);
}
const _c = new THREE.Color();

// 0 -> 1 with a small overshoot past 1 before settling: things "pop" into place
export const easeOutBack = (t) => 1 + 2.70158 * Math.pow(t - 1, 3) + 1.70158 * Math.pow(t - 1, 2);

export class Trail {
  constructor(scene) {
    this.pts = [];
    this.cols = [];
    this.born = [];
    this.mat = lineMat(0xffffff, 2.4, { vertexColors: true, opacity: 0.95 });
    this.line = null;
    this.scene = scene;
    this.dots = new THREE.InstancedMesh(new THREE.CircleGeometry(0.09, 20).rotateX(-Math.PI / 2), new THREE.MeshBasicMaterial({ transparent: true, opacity: 0.95, depthWrite: false }), 4000);
    this.dots.count = 0;
    this.dots.renderOrder = 4;
    this.dots.frustumCulled = false;
    scene.add(this.dots);
    // the last stretch, from the newest trail point to where the boat is right now
    this.tailGeo = new LineGeometry().setPositions([0, 0, 0, 0, 0, 0]);
    this.tail = new Line2(this.tailGeo, lineMat(0xe2e8f0, 1.2, { dashed: true, dashSize: 0.6, gapSize: 0.5, opacity: 0.55 }));
    this.tail.renderOrder = 4;
    this.tail.visible = false;
    scene.add(this.tail);
  }
  add(lat, lon, dbm, now) {
    const [x, z] = toXZ(lat, lon);
    const c = signalColor(dbm);
    this.pts.push(x, 0.07, z);
    this.cols.push(c.r, c.g, c.b);
    this.born.push(now);
    if (this.dots.count < this.dots.instanceMatrix.count) this.dots.setColorAt(this.dots.count++, c);
    if (this.pts.length >= 6) {
      if (this.line) { this.scene.remove(this.line); this.line.geometry.dispose(); }
      const geo = new LineGeometry().setPositions(this.pts).setColors(this.cols);
      this.line = new Line2(geo, this.mat);
      this.line.renderOrder = 3;
      this.scene.add(this.line);
    }
  }
  update(now, boatPos) {
    // newly dropped dots pop in
    const m = new THREE.Matrix4();
    for (let i = Math.max(0, this.dots.count - 6); i < this.dots.count; i++) {
      const s = easeOutBack(Math.min(1, (now - this.born[i]) / 0.45));
      m.makeScale(s, 1, s).setPosition(this.pts[i * 3], 0.075, this.pts[i * 3 + 2]);
      this.dots.setMatrixAt(i, m);
    }
    this.dots.instanceMatrix.needsUpdate = true;
    if (this.dots.instanceColor) this.dots.instanceColor.needsUpdate = true;
    const n = this.pts.length;
    if (n >= 3 && boatPos) {
      this.tailGeo.setPositions([this.pts[n - 3], 0.07, this.pts[n - 1], boatPos.x, 0.07, boatPos.z]);
      this.tail.computeLineDistances();
      this.tail.visible = true;
    }
  }
}

// ---------------------------------------------------------------------------------------------
// sweep plan: rows done go grey, rows to go stay amber, a marker buoy on the next waypoint
// ---------------------------------------------------------------------------------------------
function markerBuoy(color) {
  const g = new THREE.Group();
  const paint = new THREE.MeshStandardMaterial({ color, roughness: 0.45 });
  const dark = new THREE.MeshStandardMaterial({ color: 0x1f2328, roughness: 0.6 });
  const body = new THREE.Mesh(new THREE.CylinderGeometry(0.11, 0.17, 0.42, 20), paint); body.position.y = 0.12; g.add(body);
  const band = new THREE.Mesh(new THREE.CylinderGeometry(0.115, 0.125, 0.06, 20), dark); band.position.y = 0.26; g.add(band);
  const top = new THREE.Mesh(new THREE.ConeGeometry(0.11, 0.22, 20), paint); top.position.y = 0.44; g.add(top);
  return g;
}

export class SweepPlan {
  constructor(scene) {
    this.scene = scene;
    this.group = new THREE.Group();
    scene.add(this.group);
    this.points = [];
    this.index = -1;
    this.buoy = markerBuoy(0xf5b301);
    this.buoy.visible = false;
    scene.add(this.buoy);
  }
  set(latlons) {
    this.points = (latlons || []).map(([la, lo]) => { const [x, z] = toXZ(la, lo); return new THREE.Vector3(x, 0.09, z); });
    this.index = -1;
    this.rebuild(0);
  }
  rebuild(index) {
    if (index === this.index) return;
    this.index = index;
    this.group.traverse((o) => o.geometry?.dispose());
    this.group.clear();
    const P = this.points;
    if (!P.length) { this.buoy.visible = false; return; }
    const flat = (arr) => arr.flatMap((v) => [v.x, v.y, v.z]);
    const i = Math.max(0, Math.min(index, P.length));
    if (i >= 2) this.group.add(new Line2(new LineGeometry().setPositions(flat(P.slice(0, i))), lineMat(0x94a3b8, 1.4, { opacity: 0.35 })));
    const ahead = P.slice(Math.max(0, i - 1));
    if (ahead.length >= 2) {
      const l = new Line2(new LineGeometry().setPositions(flat(ahead)), lineMat(0xfbbf24, 1.8, { dashed: true, dashSize: 1.2, gapSize: 0.8, opacity: 0.8 }));
      l.computeLineDistances();
      this.group.add(l);
    }
    const marks = new THREE.InstancedMesh(new THREE.CircleGeometry(0.22, 16).rotateX(-Math.PI / 2), new THREE.MeshBasicMaterial({ color: 0xfbbf24, transparent: true, depthWrite: false }), P.length);
    marks.renderOrder = 4;
    const dimC = new THREE.Color(0x64748b), hotC = new THREE.Color(0xfbbf24);
    const m = new THREE.Matrix4();
    P.forEach((p, k) => { m.makeTranslation(p.x, 0.08, p.z); marks.setMatrixAt(k, m); marks.setColorAt(k, k < i ? dimC : hotC); });
    this.group.add(marks);
    if (i < P.length) this.buoy.position.set(P[i].x, 0, P[i].z);
  }
  update(t, active, heightAt) {
    // the plan stays on the water after a sweep, but faded, so it doesn't compete with the trail
    const fade = active ? 1 : 0.35;
    this.group.traverse((o) => { if (o.material) o.material.opacity = (o.material.userData.baseOpacity ??= o.material.opacity) * fade; });
    // the buoy marks the waypoint the boat is heading for, so it only shows while it's sweeping
    this.buoy.visible = !!active && this.index < this.points.length;
    if (!this.buoy.visible) return;
    const b = this.buoy.position;
    b.y = heightAt(b.x, b.z) - 0.06;
    this.buoy.rotation.set(Math.sin(t * 1.3 + b.x) * 0.07, 0, Math.sin(t * 1.1 + b.z) * 0.07);
  }
}

// ---------------------------------------------------------------------------------------------
// home: the launch point (tlm.home). A white marker buoy with a label; every trip home ends here.
// ---------------------------------------------------------------------------------------------
export class HomeMark {
  constructor(scene) {
    this.g = markerBuoy(0xf1f5f9);
    this.g.add(label('Home', 'is-home').translateY(0.9));
    this.ring = new THREE.Mesh(new THREE.RingGeometry(1.8, 2.0, 48).rotateX(-Math.PI / 2), new THREE.MeshBasicMaterial({ color: 0xf1f5f9, transparent: true, opacity: 0.35, depthWrite: false }));
    this.ring.position.y = 0.07;
    this.ring.renderOrder = 3;
    this.g.add(this.ring);
    this.g.visible = false;
    this.x = 0; this.z = 0;
    scene.add(this.g);
  }
  set(latlon) {
    if (!latlon) { this.g.visible = false; return; }
    [this.x, this.z] = toXZ(latlon[0], latlon[1]);
    this.g.position.set(this.x, 0, this.z);
    this.g.visible = true;
  }
  update(t, heightAt) {
    if (!this.g.visible) return;
    this.g.position.y = heightAt(this.x, this.z) - 0.06;
    this.ring.position.y = 0.07 - this.g.position.y;
    this.g.rotation.set(Math.sin(t * 1.2 + this.x) * 0.06, 0, Math.sin(t * 1.0 + this.z) * 0.06);
  }
}

// ---------------------------------------------------------------------------------------------
// autopilot target: where the boat is steering right now (tlm.target), in any self-driving mode
// ---------------------------------------------------------------------------------------------
export class PursuitTarget {
  constructor(scene) {
    this.geo = new LineGeometry().setPositions([0, 0, 0, 0, 0, 0]);
    this.line = new Line2(this.geo, lineMat(0xffffff, 1.2, { dashed: true, dashSize: 0.5, gapSize: 0.45, opacity: 0.7 }));
    this.line.renderOrder = 5;
    this.ring = new THREE.Mesh(new THREE.RingGeometry(0.32, 0.42, 32).rotateX(-Math.PI / 2), new THREE.MeshBasicMaterial({ color: 0xffffff, transparent: true, opacity: 0.85, depthWrite: false }));
    this.ring.renderOrder = 5;
    this.pos = new THREE.Vector3();
    this.has = false;
    scene.add(this.line, this.ring);
  }
  /** target: [lat, lon] or null; color: the mode's color */
  set(target, color) {
    this.has = !!target;
    if (!target) return;
    const [x, z] = toXZ(target[0], target[1]);
    if (this.pos.lengthSq() === 0) this.pos.set(x, 0.1, z);
    this.goal = [x, z];
    this.line.material.color.set(color);
    this.ring.material.color.set(color);
  }
  update(dt, boatPos, show) {
    const on = show && this.has && boatPos;
    this.line.visible = this.ring.visible = !!on;
    if (!on) return;
    // ease toward the newest target so the marker glides along the path instead of hopping
    const k = 1 - Math.exp(-8 * dt);
    this.pos.x += (this.goal[0] - this.pos.x) * k;
    this.pos.z += (this.goal[1] - this.pos.z) * k;
    this.ring.position.set(this.pos.x, 0.09, this.pos.z);
    this.geo.setPositions([boatPos.x, 0.1, boatPos.z, this.pos.x, 0.1, this.pos.z]);
    this.line.computeLineDistances();
  }
}

// ---------------------------------------------------------------------------------------------
// coverage grid: tiles that pop in as the boat covers them, colored by the chosen layer
// ---------------------------------------------------------------------------------------------
// perceptually even ramp (viridis), so "twice as far along" looks twice as far along
const RAMP = [0x440154, 0x3b528b, 0x21918c, 0x5ec962, 0xfde725].map((c) => new THREE.Color(c));
export function ramp(t, out = new THREE.Color()) {
  t = Math.max(0, Math.min(1, t)) * (RAMP.length - 1);
  const i = Math.min(RAMP.length - 2, Math.floor(t));
  return out.copy(RAMP[i]).lerp(RAMP[i + 1], t - i);
}
export const RAMP_CSS = RAMP.map((c) => '#' + c.getHexString());

export class Coverage {
  constructor(scene) {
    this.cap = 0;
    this.mesh = null;
    this.scene = scene;
    this.index = new Map();     // "ix,iy" -> instance
    this.cells = [];
    this.born = [];
  }
  ensure(n) {
    if (n <= this.cap) return;
    const cap = Math.max(256, this.cap * 2, n);
    const mesh = new THREE.InstancedMesh(new THREE.PlaneGeometry(1, 1).rotateX(-Math.PI / 2), new THREE.MeshBasicMaterial({ transparent: true, opacity: 0.2, depthWrite: false }), cap);
    mesh.renderOrder = 2;
    mesh.frustumCulled = false;
    if (this.mesh) { this.scene.remove(this.mesh); this.mesh.geometry.dispose(); }
    this.mesh = mesh;
    this.cap = cap;
    this.scene.add(mesh);
    this.mesh.count = 0;
    this.index.clear();
    const old = this.cells; this.cells = []; this.born = [];
    old.forEach((c) => this.upsert(c, -10));
  }
  upsert(c, now) {
    const key = c.ix + ',' + c.iy;
    let i = this.index.get(key);
    if (i === undefined) { i = this.mesh.count++; this.index.set(key, i); this.born[i] = now; }
    this.cells[i] = c;
  }
  set(grid, layer, range, now) {
    this.size = grid.size_m;
    this.ensure(grid.cells.length);
    grid.cells.forEach((c) => this.upsert(c, now));
    this.recolor(layer, range);
  }
  recolor(layer, range) {
    if (!this.mesh) return;
    const col = new THREE.Color();
    for (let i = 0; i < this.mesh.count; i++) {
      const v = this.cells[i]?.[layer];
      if (layer === 'covered' || v == null) col.set(0x67e8f9);
      else ramp((v - range[0]) / (range[1] - range[0]), col);
      this.mesh.setColorAt(i, col);
    }
    if (this.mesh.instanceColor) this.mesh.instanceColor.needsUpdate = true;
  }
  update(now) {
    if (!this.mesh) return;
    const m = new THREE.Matrix4();
    const s = this.size * 0.94;
    let changed = false;
    for (let i = 0; i < this.mesh.count; i++) {
      const age = now - this.born[i];
      if (age > 0.6 && this._settled?.[i]) continue;
      const t = Math.min(1, age / 0.5);
      const k = 1 - Math.pow(1 - t, 3);
      const c = this.cells[i];
      m.makeScale(s * k, 1, s * k).setPosition((c.ix + 0.5) * this.size, 0.04, -(c.iy + 0.5) * this.size);
      this.mesh.setMatrixAt(i, m);
      (this._settled ??= [])[i] = t >= 1;
      changed = true;
    }
    if (changed) this.mesh.instanceMatrix.needsUpdate = true;
  }
}

// ---------------------------------------------------------------------------------------------
// trash pins: small orange buoys bobbing where the operator marked trash
// ---------------------------------------------------------------------------------------------
export class TrashPins {
  constructor(scene) {
    this.scene = scene;
    this.items = [];
    this.geo = new THREE.CylinderGeometry(0.16, 0.2, 0.3, 16);
    this.capGeo = new THREE.SphereGeometry(0.16, 16, 8, 0, Math.PI * 2, 0, Math.PI / 2);
    this.mat = new THREE.MeshStandardMaterial({ color: 0xf97316, roughness: 0.5 });
    this.band = new THREE.MeshStandardMaterial({ color: 0xf1f5f9, roughness: 0.5 });
  }
  sync(list, now, onNew) {
    for (let i = this.items.length; i < list.length; i++) {
      const [x, z] = toXZ(list[i][0], list[i][1]);
      const g = new THREE.Group();
      const body = new THREE.Mesh(this.geo, this.mat); body.position.y = 0.1; g.add(body);
      const cap = new THREE.Mesh(this.capGeo, this.mat); cap.position.y = 0.25; g.add(cap);
      const band = new THREE.Mesh(new THREE.CylinderGeometry(0.185, 0.19, 0.05, 16), this.band); band.position.y = 0.14; g.add(band);
      const l = label(`Trash ${i + 1}`, 'is-trash'); l.position.y = 0.9; g.add(l);
      g.position.set(x, 0, z);
      g.scale.setScalar(0.001);
      this.scene.add(g);
      this.items.push({ g, born: now, x, z });
      onNew?.(x, z);
    }
  }
  update(now, heightAt) {
    for (const it of this.items) {
      it.g.scale.setScalar(Math.max(0.001, easeOutBack(Math.min(1, (now - it.born) / 0.6))));
      it.g.position.y = heightAt(it.x, it.z) - 0.04;
      it.g.rotation.z = Math.sin(now * 1.3 + it.x) * 0.06;
      it.g.rotation.x = Math.sin(now * 1.1 + it.z) * 0.06;
    }
  }
}
