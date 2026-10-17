// The Rev C boat at real size (meters). Bow points along -z.
//
// Layout from docs/ARCHITECTURE.md: two pontoons, a conveyor ramp between them at the bow
// (Rev C belt is 14.6 in), a collection basket behind it, an arch carrying the orange
// electronics island, a mast for the antenna, and thrusters under the stern.
//
// Nothing here is decoration for its own sake: the belt only moves when telemetry says the
// conveyor is on, the status light shows the mode the boat reports, and the whole model greys
// out when the station loses the link.

import * as THREE from 'three';

const mats = {
  hull: new THREE.MeshPhysicalMaterial({ color: 0xe6eaee, roughness: 0.32, clearcoat: 0.6, clearcoatRoughness: 0.25 }),
  stripe: new THREE.MeshStandardMaterial({ color: 0x2a3138, roughness: 0.6 }),
  alu: new THREE.MeshStandardMaterial({ color: 0xb9c0c8, metalness: 0.85, roughness: 0.32 }),
  composite: new THREE.MeshStandardMaterial({ color: 0x23272d, roughness: 0.75 }),
  island: new THREE.MeshStandardMaterial({ color: 0xe0712a, roughness: 0.5 }),
  rubber: new THREE.MeshStandardMaterial({ color: 0x141619, roughness: 0.92 }),
  slat: new THREE.MeshStandardMaterial({ color: 0x3a4048, roughness: 0.7 }),
  basket: new THREE.MeshStandardMaterial({ color: 0x1b1f24, roughness: 0.8, transparent: true, opacity: 0.45 }),
  wire: new THREE.LineBasicMaterial({ color: 0x8b949e, transparent: true, opacity: 0.8 }),
  lens: new THREE.MeshStandardMaterial({ color: 0x0a0c0e, metalness: 0.4, roughness: 0.1 }),
  status: new THREE.MeshBasicMaterial({ color: 0x38bdf8, toneMapped: false }),
  nav: new THREE.MeshBasicMaterial({ color: 0xffffff, toneMapped: false, transparent: true }),
  deck: new THREE.MeshBasicMaterial({ color: 0xffd9a8, toneMapped: false }),
};

const box = (w, h, d, mat, x, y, z) => { const m = new THREE.Mesh(new THREE.BoxGeometry(w, h, d), mat); m.position.set(x, y, z); return m; };

// wire grid on the faces of a box, for the mesh basket
function wireBox(w, h, d, step) {
  const pts = [];
  const seg = (a, b) => pts.push(new THREE.Vector3(...a), new THREE.Vector3(...b));
  const [x0, x1, y0, y1, z0, z1] = [-w / 2, w / 2, 0, h, -d / 2, d / 2];
  for (let x = x0; x <= x1 + 1e-6; x += step) { seg([x, y0, z0], [x, y1, z0]); seg([x, y0, z1], [x, y1, z1]); seg([x, y0, z0], [x, y0, z1]); }
  for (let z = z0; z <= z1 + 1e-6; z += step) { seg([x0, y0, z], [x0, y1, z]); seg([x1, y0, z], [x1, y1, z]); seg([x0, y0, z], [x1, y0, z]); }
  for (let y = y0; y <= y1 + 1e-6; y += step) { seg([x0, y, z0], [x1, y, z0]); seg([x0, y, z1], [x1, y, z1]); seg([x0, y, z0], [x0, y, z1]); seg([x1, y, z0], [x1, y, z1]); }
  return new THREE.LineSegments(new THREE.BufferGeometry().setFromPoints(pts), mats.wire);
}

export const MODE_COLORS = { DRIVEN: 0x38bdf8, AUTO: 0xfbbf24, COMING_HOME: 0xa78bfa };

export function createBoat() {
  const root = new THREE.Group();     // sits on the water at the boat's position and heading
  const hull = new THREE.Group();     // heave, pitch and roll from the waves happen here
  root.add(hull);

  // ---- pontoons ----
  for (const sx of [-0.4, 0.4]) {
    const p = new THREE.Mesh(new THREE.CapsuleGeometry(0.12, 1.0, 10, 24), mats.hull);
    p.rotation.x = Math.PI / 2;
    p.position.set(sx, 0.05, 0);
    p.scale.set(1, 1, 0.85);           // a little flatter than round
    hull.add(p);
    const stripe = new THREE.Mesh(new THREE.CapsuleGeometry(0.1215, 1.0, 10, 24), mats.stripe);
    stripe.rotation.x = Math.PI / 2;
    stripe.position.set(sx, 0.0, 0);
    stripe.scale.set(1, 1, 0.3);       // a dark waterline band
    hull.add(stripe);
    hull.add(box(0.035, 0.03, 1.02, mats.alu, sx, 0.17, 0));               // top rail
    hull.add(box(0.03, 0.12, 0.03, mats.alu, sx, -0.02, 0.6));             // thruster strut
  }
  // cross tubes
  for (const z of [-0.3, 0.42]) {
    const t = new THREE.Mesh(new THREE.CylinderGeometry(0.018, 0.018, 0.86, 12), mats.alu);
    t.rotation.z = Math.PI / 2; t.position.set(0, 0.19, z); hull.add(t);
  }
  hull.add(box(0.62, 0.012, 0.3, mats.composite, 0, 0.19, 0.5));           // stern deck plate

  // ---- conveyor: hinged at the top, belt runs up from the waterline at the bow ----
  const conveyor = new THREE.Group();
  const L = 0.7, angle = Math.atan2(0.36, 0.58);
  conveyor.position.set(0, 0.34, -0.08);
  conveyor.rotation.x = -angle;
  hull.add(conveyor);
  conveyor.add(box(0.36, 0.012, L, mats.rubber, 0, 0, -L / 2));
  for (const sx of [-0.195, 0.195]) conveyor.add(box(0.012, 0.07, L + 0.04, mats.alu, sx, 0.02, -L / 2));
  for (const z of [0, -L]) {
    const r = new THREE.Mesh(new THREE.CylinderGeometry(0.022, 0.022, 0.37, 14), mats.alu);
    r.rotation.z = Math.PI / 2; r.position.set(0, -0.01, z); conveyor.add(r);
  }
  const SLATS = 12;
  const slats = new THREE.InstancedMesh(new THREE.BoxGeometry(0.34, 0.014, 0.014), mats.slat, SLATS);
  conveyor.add(slats);
  let beltPhase = 0;
  const _m = new THREE.Matrix4();
  const placeSlats = () => {
    for (let i = 0; i < SLATS; i++) {
      const u = (beltPhase + i / SLATS) % 1;
      _m.makeTranslation(0, 0.013, -L + u * L);
      slats.setMatrixAt(i, _m);
    }
    slats.instanceMatrix.needsUpdate = true;
  };
  placeSlats();

  // ---- basket behind the conveyor ----
  const basket = new THREE.Group();
  basket.position.set(0, 0.1, 0.13);
  basket.add(box(0.42, 0.22, 0.36, mats.basket, 0, 0.11, 0));
  basket.add(wireBox(0.42, 0.22, 0.36, 0.06));
  hull.add(basket);

  // ---- arch, electronics island, mast ----
  for (const sx of [-0.4, 0.4]) hull.add(box(0.03, 0.44, 0.03, mats.alu, sx, 0.4, 0.42));
  hull.add(box(0.83, 0.03, 0.03, mats.alu, 0, 0.62, 0.42));
  hull.add(box(0.16, 0.09, 0.13, mats.island, 0, 0.68, 0.42));
  hull.add(box(0.165, 0.008, 0.135, mats.composite, 0, 0.727, 0.42));      // lid seam
  const status = box(0.004, 0.012, 0.07, mats.status, 0.082, 0.69, 0.42); // mode light on the side
  hull.add(status);
  const status2 = status.clone(); status2.position.x = -0.082; hull.add(status2);
  const gps = new THREE.Mesh(new THREE.CylinderGeometry(0.03, 0.03, 0.014, 20), mats.composite);
  gps.position.set(0.045, 0.738, 0.45); hull.add(gps);
  const mast = new THREE.Mesh(new THREE.CylinderGeometry(0.009, 0.011, 0.42, 10), mats.alu);
  mast.position.set(-0.03, 0.94, 0.42); hull.add(mast);
  const whip = new THREE.Mesh(new THREE.CylinderGeometry(0.005, 0.007, 0.2, 8), mats.rubber);
  whip.position.set(-0.03, 1.25, 0.42); hull.add(whip);
  const nav = new THREE.Mesh(new THREE.SphereGeometry(0.016, 12, 8), mats.nav);
  nav.position.set(-0.03, 1.152, 0.42); hull.add(nav);
  // a deck light under the island, so the belt and basket are lit at dusk (and it reads as a working boat)
  const deckLight = new THREE.PointLight(0xffd9a8, 1.2, 3.5, 1.8); deckLight.position.set(0, 0.62, 0.2); hull.add(deckLight);
  const deckBulb = new THREE.Mesh(new THREE.SphereGeometry(0.012, 8, 6), mats.deck); deckBulb.position.set(0, 0.63, 0.34); hull.add(deckBulb);
  // front camera on the island, rear camera at the stern
  hull.add(box(0.05, 0.035, 0.035, mats.composite, 0, 0.68, 0.34));
  const lens = new THREE.Mesh(new THREE.CylinderGeometry(0.011, 0.011, 0.012, 16), mats.lens);
  lens.rotation.x = Math.PI / 2; lens.position.set(0, 0.68, 0.318); hull.add(lens);
  hull.add(box(0.035, 0.03, 0.03, mats.composite, 0, 0.22, 0.64));

  // remember original colors so the boat can grey out and come back
  const tinted = [mats.hull, mats.island, mats.alu, mats.composite, mats.basket];
  const base = tinted.map((m) => m.color.clone());
  let grey = 0;

  return {
    root, hull,
    // where effects come from, in the hull's local frame
    anchors: {
      thrusterL: new THREE.Vector3(-0.4, 0.02, 0.66),
      thrusterR: new THREE.Vector3(0.4, 0.02, 0.66),
      bowL: new THREE.Vector3(-0.44, 0.02, -0.56),
      bowR: new THREE.Vector3(0.44, 0.02, -0.56),
      intake: new THREE.Vector3(0, 0.02, -0.68),
      beltTop: new THREE.Vector3(0, 0.36, -0.06),
      mast: new THREE.Vector3(-0.03, 1.15, 0.42),
    },
    setMode(mode) { mats.status.color.set(MODE_COLORS[mode] ?? 0x94a3b8); },
    /** conveyor: 0..1 smoothed on/off; lost: 0..1 how grey */
    update(dt, t, conveyorOn, lost) {
      if (conveyorOn > 0.01) { beltPhase = (beltPhase + dt * 0.55 * conveyorOn) % 1; placeSlats(); }
      // nav light: short double blink, like a real strobe
      const ph = t % 2.0;
      mats.nav.opacity = ph < 0.08 || (ph > 0.22 && ph < 0.3) ? 1 : 0.15;
      if (Math.abs(lost - grey) > 0.002) {
        grey = lost;
        tinted.forEach((m, i) => {
          const c = base[i];
          const l = c.r * 0.3 + c.g * 0.59 + c.b * 0.11;
          m.color.setRGB(c.r + (l * 0.6 - c.r) * grey, c.g + (l * 0.6 - c.g) * grey, c.b + (l * 0.6 - c.b) * grey);
        });
      }
    },
  };
}
