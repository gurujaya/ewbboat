// The chart: a north-up 2D map of the lake in the side panel. What an operator actually steers
// by: where the boat is relative to the station, the fence, the sweep and the trail home.
// Click anywhere on it to point the 3D camera there.

import * as THREE from 'three';
import { shoreZ } from './surface.js';
import { toXZ } from './geo.js';

const MODE_HEX = { DRIVEN: '#8fd3ff', AUTO: '#f2c66d', COMING_HOME: '#c4b1ff' };

export class Minimap {
  constructor(canvas) {
    this.c = canvas;
    this.ctx = canvas.getContext('2d');
    this.fence = null;
    this.sweepCorners = null;
    this.sweepPoints = [];
    this.view = 'area';            // 'area': the whole fence; 'boat': 60 m round the boat
    this.center = { x: 0, z: -40 };
    this.span = 340;               // meters across the canvas (eased)
    this.nextDraw = 0;
    this.colorCache = [];
    this.onPick = null;
    canvas.addEventListener('click', (e) => {
      const r = canvas.getBoundingClientRect();
      const p = this.toWorld(e.clientX - r.left, e.clientY - r.top, r.width, r.height);
      this.onPick?.(p.x, p.z);
    });
  }

  setWorld(fence, sweepCorners, sweepPoints) {
    this.fence = fence;
    this.sweepCorners = sweepCorners ? sweepCorners.map(([la, lo]) => toXZ(la, lo)) : null;
    this.sweepPoints = sweepPoints || [];
  }

  // canvas px <-> lake meters (x east, z south)
  scale(w) { return w / this.span; }
  toPx(x, z, w, h) { const s = this.scale(w); return [w / 2 + (x - this.center.x) * s, h / 2 + (z - this.center.z) * s]; }
  toWorld(px, py, w, h) { const s = this.scale(w); return { x: this.center.x + (px - w / 2) / s, z: this.center.z + (py - h / 2) / s }; }

  draw(t, st) {
    if (t < this.nextDraw) return;            // 20 fps is plenty for a chart
    this.nextDraw = t + 0.05;
    const c = this.c, dpr = Math.min(2, devicePixelRatio);
    const w = c.clientWidth, h = c.clientHeight;
    if (!w || !h) return;
    if (c.width !== Math.round(w * dpr)) { c.width = Math.round(w * dpr); c.height = Math.round(h * dpr); }
    const g = this.ctx;
    g.setTransform(dpr, 0, 0, dpr, 0, 0);

    // where to look: the whole fenced area, or close in on the boat
    let want, span;
    if (this.view === 'boat' && st.boat) { want = { x: st.boat.x, z: st.boat.z }; span = 70; }
    else {
      const r = this.fence?.r ?? 150;
      want = { x: 0, z: -r * 0.45 }; span = r * 2.15;
      // boat outside the fence: zoom out enough to keep it on the chart
      if (st.boat && Math.hypot(st.boat.x, st.boat.z) > r * 0.95) {
        want = { x: st.boat.x * 0.5, z: st.boat.z * 0.5 };
        span = Math.max(span, Math.hypot(st.boat.x, st.boat.z) * 1.4);
      }
    }
    const k = 0.25;
    this.center.x += (want.x - this.center.x) * k; this.center.z += (want.z - this.center.z) * k;
    this.span += (span - this.span) * k;

    const P = (x, z) => this.toPx(x, z, w, h);
    const s = this.scale(w);

    // water and land
    g.fillStyle = '#0c1b22'; g.fillRect(0, 0, w, h);
    g.beginPath();
    const x0 = this.toWorld(0, 0, w, h).x, x1 = this.toWorld(w, 0, w, h).x;
    for (let i = 0; i <= 60; i++) { const x = x0 + ((x1 - x0) * i) / 60; const [px, py] = P(x, shoreZ(x)); i ? g.lineTo(px, py) : g.moveTo(px, py); }
    g.lineTo(w, h); g.lineTo(0, h); g.closePath();
    g.fillStyle = '#1d231b'; g.fill();
    g.strokeStyle = 'rgba(214, 196, 160, 0.45)'; g.lineWidth = 1; g.stroke();

    // range rings every 50 m, labeled
    g.font = '500 9.5px "JetBrains Mono Var", ui-monospace, monospace';
    g.textAlign = 'left'; g.textBaseline = 'middle';
    const [sx, sy] = P(0, 0);
    for (let r = 50; r <= 400; r += 50) {
      if (r * s < 14) continue;
      g.beginPath(); g.arc(sx, sy, r * s, Math.PI, 2 * Math.PI);
      g.strokeStyle = 'rgba(186, 230, 253, 0.10)'; g.stroke();
      const [lx, ly] = P(r * 0.34, -r * 0.94);
      g.fillStyle = 'rgba(203, 213, 225, 0.45)'; g.fillText(`${r}`, lx + 3, ly);
    }

    // fence
    g.setLineDash([5, 4]);
    g.strokeStyle = 'rgba(125, 211, 252, 0.75)'; g.lineWidth = 1.3;
    if (this.fence?.r) { g.beginPath(); g.arc(sx, sy, this.fence.r * s, 0, Math.PI * 2); g.stroke(); }
    else if (this.fence) { const [a, b] = P(this.fence.x0, this.fence.z0), [cc, d] = P(this.fence.x1, this.fence.z1); g.strokeRect(a, b, cc - a, d - b); }
    // sweep area and plan
    if (this.sweepCorners) {
      const [[ax, az], [bx, bz]] = this.sweepCorners;
      const [a, b] = P(ax, az), [cc, d] = P(bx, bz);
      g.strokeStyle = 'rgba(251, 191, 36, 0.9)'; g.strokeRect(a, b, cc - a, d - b);
      g.fillStyle = 'rgba(251, 191, 36, 0.06)'; g.fillRect(a, b, cc - a, d - b);
    }
    g.setLineDash([]);
    const sp = this.sweepPoints;
    if (sp.length > 1) {
      const done = Math.max(0, Math.min(st.sweepIndex ?? 0, sp.length));
      g.lineWidth = 1;
      g.beginPath(); sp.slice(0, done + 1).forEach((p, i) => { const [x, y] = P(p.x, p.z); i ? g.lineTo(x, y) : g.moveTo(x, y); });
      g.strokeStyle = 'rgba(148, 163, 184, 0.45)'; g.stroke();
      g.beginPath(); sp.slice(Math.max(0, done - 1)).forEach((p, i) => { const [x, y] = P(p.x, p.z); i ? g.lineTo(x, y) : g.moveTo(x, y); });
      g.strokeStyle = 'rgba(251, 191, 36, 0.7)'; g.stroke();
    }

    // trail, colored by the signal at each point
    const T = st.trail, n = T.length / 3;
    for (let i = this.colorCache.length; i < n; i++) {
      this.colorCache.push('#' + new THREE.Color(st.trailCols[i * 3], st.trailCols[i * 3 + 1], st.trailCols[i * 3 + 2]).getHexString());
    }
    g.lineWidth = 2; g.lineCap = 'round';
    for (let i = 1; i < n; i++) {
      const [ax, ay] = P(T[(i - 1) * 3], T[(i - 1) * 3 + 2]), [bx, by] = P(T[i * 3], T[i * 3 + 2]);
      g.strokeStyle = this.colorCache[i]; g.beginPath(); g.moveTo(ax, ay); g.lineTo(bx, by); g.stroke();
    }

    // floating trash (sim only): small pale dots
    g.fillStyle = 'rgba(226, 232, 240, 0.55)';
    for (const it of st.flotsam || []) { const [x, y] = P(it.x, it.z); g.fillRect(x - 1, y - 1, 2, 2); }
    // trash pins
    for (const it of st.trash) { const [x, y] = P(it.x, it.z); g.fillStyle = '#f97316'; g.beginPath(); g.arc(x, y, 3, 0, Math.PI * 2); g.fill(); }

    // home (launch point)
    if (st.home) { const [hx, hy] = P(st.home.x, st.home.z); g.strokeStyle = '#f1f5f9'; g.lineWidth = 1.5; g.beginPath(); g.arc(hx, hy, 4, 0, Math.PI * 2); g.stroke(); g.beginPath(); g.moveTo(hx - 2, hy); g.lineTo(hx + 2, hy); g.moveTo(hx, hy - 2); g.lineTo(hx, hy + 2); g.stroke(); }
    // station
    g.fillStyle = '#e2e8f0'; g.fillRect(sx - 3.5, sy - 3.5, 7, 7);
    g.strokeStyle = '#0c1b22'; g.lineWidth = 1.5; g.strokeRect(sx - 3.5, sy - 3.5, 7, 7);

    // where the autopilot is steering
    if (st.boat && st.target) {
      const [bx, by] = P(st.boat.x, st.boat.z), [tx, ty] = P(st.target.x, st.target.z);
      g.setLineDash([3, 3]); g.strokeStyle = 'rgba(255,255,255,0.7)'; g.lineWidth = 1;
      g.beginPath(); g.moveTo(bx, by); g.lineTo(tx, ty); g.stroke(); g.setLineDash([]);
      g.beginPath(); g.arc(tx, ty, 3, 0, Math.PI * 2); g.stroke();
    }

    // the boat: an arrow in its mode color, pointing along its heading
    if (st.boat) {
      const [bx, by] = P(st.boat.x, st.boat.z);
      g.save(); g.translate(bx, by); g.rotate((st.boat.h * Math.PI) / 180);
      g.beginPath(); g.moveTo(0, -8); g.lineTo(5.5, 6); g.lineTo(0, 3.2); g.lineTo(-5.5, 6); g.closePath();
      g.fillStyle = st.lost ? '#f87171' : MODE_HEX[st.mode] ?? '#e2e8f0';
      g.strokeStyle = '#0c1b22'; g.lineWidth = 1.5; g.fill(); g.stroke();
      g.restore();
    }

    // scale bar and north arrow
    const bar = [10, 20, 50, 100, 200].find((m) => m * s > 46) ?? 200;
    g.fillStyle = 'rgba(226, 232, 240, 0.85)'; g.fillRect(10, h - 12, bar * s, 2);
    g.fillText(`${bar} m`, 10 + bar * s + 6, h - 11);
    g.textAlign = 'center'; g.fillText('N', w - 14, 14);
    g.beginPath(); g.moveTo(w - 14, 20); g.lineTo(w - 14, 32); g.strokeStyle = 'rgba(226,232,240,0.6)'; g.lineWidth = 1; g.stroke();
  }
}
