// SIM ONLY. Floating trash in the lake, from the simulator's ground-truth feed
// (sim/fake_arduino.py serves it; see sim/README.md "Trash"). The real boat has no idea where
// the trash is, so nothing here feeds back into control: it's for looking at, and for counting
// what the conveyor actually scooped. With no feed (the real boat) this stays empty and silent.

import * as THREE from 'three';
import { toXZ } from './geo.js';

const POLL_MS = 250;

export class TruthFeed {
  constructor(onData, onLost, fetcher = null) {
    this.fetcher = fetcher;               // the in-browser sim answers directly, no HTTP
    const port = new URLSearchParams(location.search).get('truth') || '8099';
    // the station passes the feed through on its own origin (that's all a public host exposes);
    // on a laptop the fake Arduino's own port works too
    this.urls = [new URL('../api/sim/truth', location.href).href, `${location.protocol}//${location.hostname}:${port}/truth`];
    this.which = 0;
    this.onData = onData;
    this.onLost = onLost;
    this.live = false;
    this.fails = 0;
    this.poll();
  }
  async poll() {
    try {
      let d;
      if (this.fetcher) d = await this.fetcher();
      else {
        const r = await fetch(this.urls[this.which], { cache: 'no-store' });
        if (!r.ok) throw new Error(r.status);
        d = await r.json();
      }
      this.fails = 0;
      if (!this.live) { this.live = true; }
      this.onData(d);
      setTimeout(() => this.poll(), POLL_MS);
    } catch {
      // no feed: that's the real boat (or the sim without --truth-port). Try the other URL, then
      // again later, quietly.
      this.fails++;
      this.which = 1 - this.which;
      if (this.live && this.fails >= 3) { this.live = false; this.onLost(); }
      setTimeout(() => this.poll(), this.live ? POLL_MS : 5000);
    }
  }
}

// small, recognisable shapes; sizes in meters
const mats = {
  bottle: new THREE.MeshPhysicalMaterial({ color: 0xd9f0ff, transparent: true, opacity: 0.75, roughness: 0.15, transmission: 0.3 }),
  cap: new THREE.MeshStandardMaterial({ color: 0x2563eb, roughness: 0.5 }),
  bag: new THREE.MeshStandardMaterial({ color: 0xf8fafc, roughness: 0.9, side: THREE.DoubleSide, transparent: true, opacity: 0.85 }),
  cup: new THREE.MeshStandardMaterial({ color: 0xfef3c7, roughness: 0.7 }),
  can: new THREE.MeshStandardMaterial({ color: 0xb91c1c, metalness: 0.6, roughness: 0.35 }),
  lid: new THREE.MeshStandardMaterial({ color: 0xcbd5e1, metalness: 0.8, roughness: 0.3 }),
};
const markGeo = new THREE.RingGeometry(0.3, 0.38, 24).rotateX(-Math.PI / 2);
const markMat = new THREE.MeshBasicMaterial({ color: 0xffffff, transparent: true, opacity: 0.4, depthWrite: false });

const geos = {
  bottle: new THREE.CapsuleGeometry(0.035, 0.18, 4, 10).rotateZ(Math.PI / 2),
  cap: new THREE.CylinderGeometry(0.015, 0.015, 0.02, 10).rotateZ(Math.PI / 2),
  bag: new THREE.IcosahedronGeometry(0.14, 1).scale(1, 0.35, 0.8),
  cup: new THREE.CylinderGeometry(0.045, 0.032, 0.1, 12).rotateZ(Math.PI / 2.4),
  can: new THREE.CylinderGeometry(0.033, 0.033, 0.12, 14).rotateZ(Math.PI / 2),
  lid: new THREE.CylinderGeometry(0.034, 0.034, 0.004, 14).rotateZ(Math.PI / 2),
};

function piece(kind) {
  const g = new THREE.Group();
  const add = (geo, mat, y = 0, x = 0) => { const m = new THREE.Mesh(geos[geo], mats[mat]); m.position.set(x, y, 0); g.add(m); return m; };
  if (kind === 'bottle') { add('bottle', 'bottle', 0.01); add('cap', 'cap', 0.01, 0.125); }
  else if (kind === 'bag') { const m = add('bag', 'bag', 0.02); m.rotation.y = Math.random() * 3; }
  else if (kind === 'cup') add('cup', 'cup', 0.02);
  else { add('can', 'can', 0.01); add('lid', 'lid', 0.01, 0.062); }
  g.rotation.y = Math.random() * Math.PI * 2;
  g.userData.spin = (Math.random() - 0.5) * 0.3;
  g.scale.setScalar(1.5);      // a touch over life size: real litter all but vanishes from 15 m away
  return g;
}

export class Flotsam {
  constructor(scene, onCollected) {
    this.scene = scene;
    this.items = new Map();        // id -> { g, kind, x, z, tx, tz, collected, pickAt, from }
    this.total = 0;
    this.collected = 0;
    this.onCollected = onCollected;
  }
  /** one snapshot of the truth feed. boatDrawn: where the page draws the boat (its GPS estimate);
   * the feed also has the boat's TRUE position. The difference is the GPS error of the moment,
   * and the trash is drawn shifted by the same amount, so a piece passes under the drawn hull
   * exactly when the real piece passes under the real hull. Relative geometry stays honest. */
  set(d, now, boatDrawn) {
    this.total = d.total ?? 0;
    this.collected = d.collected ?? 0;
    let ox = 0, oz = 0;
    if (d.boat && boatDrawn) {
      const [bx, bz] = toXZ(d.boat.lat, d.boat.lon);
      // ease the shift so a GPS step doesn't make the whole lake jump
      this.ox = (this.ox ?? 0) + ((boatDrawn.x - bx) - (this.ox ?? 0)) * 0.3;
      this.oz = (this.oz ?? 0) + ((boatDrawn.z - bz) - (this.oz ?? 0)) * 0.3;
      ox = this.ox; oz = this.oz;
    }
    const seen = new Set();
    for (const t of d.trash || []) {
      seen.add(t.id);
      let [x, z] = toXZ(t.lat, t.lon);
      x += ox; z += oz;
      let it = this.items.get(t.id);
      if (!it) {
        it = { g: piece(t.kind), kind: t.kind, x, z, tx: x, tz: z, collected: false, pickAt: 0, mark: new THREE.Mesh(markGeo, markMat) };
        it.g.position.set(x, 0, z);
        it.mark.renderOrder = 4;
        this.scene.add(it.g, it.mark);
        this.items.set(t.id, it);
      }
      it.tx = x; it.tz = z;
      if (t.collected && !it.collected) {
        it.collected = true;
        it.pickAt = now;
        it.from = [it.x, it.z];
        this.onCollected?.(it.x, it.z);
        it.mark.visible = false;
      }
    }
    for (const [id, it] of this.items) if (!seen.has(id)) { this.scene.remove(it.g, it.mark); this.items.delete(id); }
  }
  clear() {
    for (const it of this.items.values()) this.scene.remove(it.g, it.mark);
    this.items.clear();
    this.total = this.collected = 0;
  }
  /** beltTop: world position of the top of the conveyor, where a collected piece disappears into the basket */
  update(dt, now, heightAt, beltTop, camPos) {
    const k = 1 - Math.exp(-6 * dt);
    for (const it of this.items.values()) {
      // a faint ring on the water under each piece, only once the camera is too far to see the
      // piece itself (sim aid: on the lake you'd be looking at the camera feed, not GPS)
      if (!it.collected && camPos) {
        const d = Math.hypot(camPos.x - it.x, camPos.z - it.z);
        it.mark.visible = d > 12;
        it.mark.material.opacity = Math.min(0.5, (d - 12) / 40);
        it.mark.position.set(it.x, 0.06, it.z);
        it.mark.scale.setScalar(Math.max(1, d / 25));
      }
      const g = it.g;
      if (it.collected) {
        // ride up the belt: from where it was scooped to the top of the conveyor, then it's in the basket
        const u = Math.min(1, (now - it.pickAt) / 0.9);
        if (u >= 1) { g.visible = false; continue; }
        const e = u * u * (3 - 2 * u);
        g.position.set(it.from[0] + (beltTop.x - it.from[0]) * e, 0.02 + (beltTop.y - 0.02) * e, it.from[1] + (beltTop.z - it.from[1]) * e);
        g.scale.setScalar(1.5 * (1 - 0.5 * u));
        continue;
      }
      it.x += (it.tx - it.x) * k;
      it.z += (it.tz - it.z) * k;
      g.position.set(it.x, heightAt(it.x, it.z), it.z);
      g.rotation.y += g.userData.spin * dt;
      g.rotation.x = Math.sin(now * 1.4 + it.x) * 0.12;
      g.rotation.z = Math.sin(now * 1.1 + it.z) * 0.12;
    }
  }
  /** for the chart: positions of the pieces still in the water */
  floating() {
    const out = [];
    for (const it of this.items.values()) if (!it.collected) out.push(it);
    return out;
  }
}
