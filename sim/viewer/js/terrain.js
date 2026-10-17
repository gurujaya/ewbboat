// Land: the bank the station stands on, and the far shore across the lake with its tree line.
//
// Both are real height fields (geometry, not paint), so they catch the low sun, cast a proper
// silhouette, and show up upside down in the water's mirror. heightAt() is exported so things
// placed on the bank (station, jetty) sit on the ground instead of floating.

import * as THREE from 'three';
import { shoreZ } from './surface.js';

// small deterministic value noise, so the landscape is the same every time the page loads
function hash(x, z) { const s = Math.sin(x * 127.1 + z * 311.7) * 43758.5453; return s - Math.floor(s); }
function noise(x, z) {
  const xi = Math.floor(x), zi = Math.floor(z), xf = x - xi, zf = z - zi;
  const u = xf * xf * (3 - 2 * xf), v = zf * zf * (3 - 2 * zf);
  const a = hash(xi, zi), b = hash(xi + 1, zi), c = hash(xi, zi + 1), d = hash(xi + 1, zi + 1);
  return a + (b - a) * u + (c - a) * v + (a - b - c + d) * u * v;
}
function fbm(x, z, oct = 4) { let s = 0, a = 0.5, f = 1; for (let i = 0; i < oct; i++) { s += a * noise(x * f, z * f); f *= 2.03; a *= 0.5; } return s; }
const smooth = (a, b, x) => { const t = Math.max(0, Math.min(1, (x - a) / (b - a))); return t * t * (3 - 2 * t); };

// ---- the near bank (south of the water) ----
export function heightAt(x, z) {
  const d = z - shoreZ(x);                       // meters inland from the waterline
  if (d < 0) return d * 0.22 + 0.02;             // the bank keeps going down under the water
  let h = 0.02 + 0.28 * smooth(0, 2.0, d);       // a little sandy berm at the waterline
  h += 1.6 * smooth(4, 30, d) * (0.7 + 0.6 * fbm(x * 0.02, z * 0.02));
  h += 0.25 * fbm(x * 0.15, z * 0.15) * smooth(2, 8, d);
  // a flat pad for the station
  const pad = smooth(6, 2.5, Math.hypot(x, z));
  h = h * (1 - pad) + 0.32 * pad;
  // woods well back from the water: canopy bumps that read as trees from the lake
  const woods = smooth(55, 80, d);
  h += woods * (5 + 9 * fbm(x * 0.05, z * 0.05) + 3 * fbm(x * 0.35, z * 0.35));
  return h;
}

function nearColor(x, z, h, out) {
  const d = z - shoreZ(x);
  const n = fbm(x * 0.3, z * 0.3);
  const wet = [0.22, 0.2, 0.16], sand = [0.5, 0.45, 0.36], grass = [0.2 + 0.06 * n, 0.27 + 0.06 * n, 0.13], wood = [0.08, 0.13, 0.07];
  const mix = (a, b, t) => a.map((v, i) => v + (b[i] - v) * t);
  let c = mix(wet, sand, smooth(-0.2, 1.2, d));
  c = mix(c, grass, smooth(2.5 + n * 2, 6 + n * 3, d));
  c = mix(c, wood, smooth(52, 70, d));
  if (Math.hypot(x, z) < 3.5) c = mix(c, [0.36, 0.34, 0.3], 0.6);   // gravel round the station
  return out.setRGB(c[0], c[1], c[2], THREE.SRGBColorSpace);
}

// ---- the far shore (north), mostly a tree line in the haze ----
const farShoreZ = (x) => -390 + 45 * Math.sin(x * 0.0042 + 1.1) + 18 * Math.sin(x * 0.013);
function farHeight(x, z) {
  const d = farShoreZ(x) - z;                    // meters inland, going north
  if (d < 0) return d * 0.3 - 0.05;
  return 1.0 * smooth(0, 6, d) + smooth(8, 30, d) * (7 + 10 * fbm(x * 0.012, z * 0.012) + 4 * fbm(x * 0.08, z * 0.08)) + 30 * smooth(150, 600, d) * fbm(x * 0.002, z * 0.002);
}

function heightField(w, d, segW, segD, cx, cz, hFn, colorFn) {
  const geo = new THREE.PlaneGeometry(w, d, segW, segD).rotateX(-Math.PI / 2);
  geo.translate(cx, 0, cz);
  const pos = geo.attributes.position;
  const colors = new Float32Array(pos.count * 3);
  const c = new THREE.Color();
  for (let i = 0; i < pos.count; i++) {
    const x = pos.getX(i), z = pos.getZ(i);
    const h = hFn(x, z);
    pos.setY(i, h);
    colorFn(x, z, h, c);
    colors.set([c.r, c.g, c.b], i * 3);
  }
  geo.setAttribute('color', new THREE.BufferAttribute(colors, 3));
  geo.computeVertexNormals();
  return geo;
}

export function createTerrain(scene) {
  const mat = new THREE.MeshStandardMaterial({ vertexColors: true, roughness: 0.96, metalness: 0 });
  // near bank: 1 m detail where you'll look closely, coarser further back
  const near = new THREE.Mesh(heightField(600, 150, 600, 150, 0, 60, heightAt, nearColor), mat);
  // the rest of the bank at 10 m detail; where the detailed patch already is, it sits half a
  // meter lower so the two never fight over the same pixels
  const inNear = (x, z) => Math.abs(x) < 299 && z < 134;
  const back = new THREE.Mesh(heightField(2400, 1045, 240, 105, 0, 507.5, (x, z) => heightAt(x, z) - (inNear(x, z) ? 0.5 : 0), nearColor), mat);
  const farColor = (x, z, h, out) => {
    const d = farShoreZ(x) - z;
    const n = fbm(x * 0.05, z * 0.05);
    if (d < 4) return out.setRGB(0.3, 0.27, 0.21, THREE.SRGBColorSpace);
    return out.setRGB(0.06 + 0.04 * n, 0.1 + 0.05 * n, 0.06, THREE.SRGBColorSpace);
  };
  const far = new THREE.Mesh(heightField(4000, 1200, 400, 120, 0, -900, farHeight, farColor), mat);
  for (const m of [near, back, far]) scene.add(m);
  return { near, back, far };
}
