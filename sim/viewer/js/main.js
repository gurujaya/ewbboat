// Station view: wires the station's WebSocket (/ws) to the 3D scene and the panels.
//
// It only shows what the station knows. Telemetry arrives a few times a second (filtered
// position from the boat); the boat is drawn a moment in the past, blended between real fixes
// (see `est`). Effects come from real fields: prop wash from tlm.left/right, the belt and
// droplets from tlm.conveyor, wakes from the boat's motion, the white aim line from tlm.target.
//
// Message formats: docs/MESSAGES.md. Browser -> station messages: ground-station/main.py handle().

import * as THREE from 'three';
import { OrbitControls } from 'three/addons/controls/OrbitControls.js';
import { Line2 } from 'three/addons/lines/Line2.js';
import { LineGeometry } from 'three/addons/lines/LineGeometry.js';
import { setOrigin, toXZ, toLatLon, headingToYaw, wrapDeg, damp } from './geo.js';
import { waveHeight, waveSlope } from './surface.js';
import { createRenderer, createEnvironment, createStation, rectFence, circleFence, Trail, SweepPlan, PursuitTarget, HomeMark, Coverage, TrashPins, label, lineMat, RAMP_CSS } from './world.js';
import { heightAt } from './terrain.js';
import { Minimap } from './minimap.js';
import { Flotsam, TruthFeed } from './flotsam.js';
import { createBoat, MODE_COLORS } from './boat.js';
import { Particles, Rate } from './particles.js';
import * as ui from './ui.js';

const { animate } = window.Motion;
const reduceMotion = matchMedia('(prefers-reduced-motion: reduce)').matches;

// ---------------------------------------------------------------------------------------------
// scene
// ---------------------------------------------------------------------------------------------
const canvas = ui.$('scene');
const { renderer, labels } = createRenderer(canvas, ui.$('labels'));
const scene = new THREE.Scene();
const camera = new THREE.PerspectiveCamera(50, 1, 0.3, 12000);
camera.position.set(9, 7, 2);
const env = createEnvironment(renderer, scene);
const station = createStation(scene);

const controls = new OrbitControls(camera, canvas);
controls.enableDamping = true;
controls.dampingFactor = 0.08;
controls.maxPolarAngle = THREE.MathUtils.degToRad(86);
controls.minDistance = 2.5;
controls.maxDistance = 1200;
controls.target.set(0, 0, -15);

const boat = createBoat();
scene.add(boat.root);
const boatLabel = label('', 'is-boat');
boatLabel.position.set(0, 2.2, 0);
boat.root.add(boatLabel);

for (const r of [50, 100, 150, 200]) {
  const l = label(`${r} m`, 'is-ring');
  l.position.set(r * Math.sin(0.35), 0.1, -r * Math.cos(0.35));
  l.center.set(0.5, 0.5);
  scene.add(l);
}

const trail = new Trail(scene);
const sweep = new SweepPlan(scene);
const coverage = new Coverage(scene);
const trash = new TrashPins(scene);
const pursuit = new PursuitTarget(scene);
const home = new HomeMark(scene);
// SIM ONLY: floating trash from the simulator's ground-truth feed (silent when there is none)
const flotsam = new Flotsam(scene, (x, z) => ripple(x, z, 0xffffff, 1.6, 0.9, 0.5));
let truth = null;
function startTruth() {
  truth = new TruthFeed(
    (d) => { flotsam.set(d, now(), est.has ? { x: est.x, z: est.z } : null); ui.setTrash(flotsam.collected, flotsam.total, true); },
    () => { flotsam.clear(); ui.setTrash(0, 0, false); },
    localTruth,
  );
}
const minimap = new Minimap(ui.$('minimap'));
let drivenFence = null, sweepFence = null, fence = null;   // fence: { r } circle or { x0, x1, z0, z1 } box

// particles
const foam = new Particles(9000, 'foam', { renderOrder: 2 });
const spray = new Particles(2000, 'spray', { renderOrder: 5 });
const rings = new Particles(96, 'ring', { renderOrder: 3 });
scene.add(foam.mesh, spray.mesh, rings.mesh);

// ---------------------------------------------------------------------------------------------
// state
// ---------------------------------------------------------------------------------------------
const S = {
  me: null, holder: null,
  tlm: null, tlmAt: 0,
  socket: false, link: true, linkLostAt: 0, lastMsgAt: 0,
  pending: null,                 // { mode, at } after a mode button, until the boat answers
  layer: 'covered', grid: null,
  conveyorCmd: false,
  pick: 0, corner1: null,        // sweep picking: 0 off, 1 waiting for corner 1, 2 for corner 2
  camMode: 'follow',
  fenceWarned: false,
};
const now = () => performance.now() / 1000;

// ---------------------------------------------------------------------------------------------
// where to draw the boat: snapshot interpolation, the way networked games do it.
//
// Keep the last few fixes and draw the boat a short moment in the past, blending between the two
// real fixes either side of that moment. Every frame shows a position the boat actually reported
// (or a smooth curve between two of them), so nothing is guessed and nothing snaps. The delay
// adapts to how often fixes arrive: about 0.3 s at 5 Hz, longer if the link slows down.
// ---------------------------------------------------------------------------------------------
const est = {
  buf: [],                              // { t, x, z, h } newest last; h is unwrapped (no 359 -> 0 jump)
  has: false, x: 0, z: -15, h: 0,       // what we draw
  interval: 0.2, delay: 0.35,
  speed: 0, yawRate: 0,
  vx: 0, vz: 0, prevX: 0, prevZ: 0,     // drawn velocity, for wakes
  left: 0, right: 0, conveyor: 0, lost: 0,
  onFix(x, z, h, speed, t) {
    const last = this.buf.at(-1);
    if (last) {
      const dt = t - last.t;
      if (dt < 0.01) return;
      this.interval += (Math.min(dt, 2) - this.interval) * 0.2;
      h = last.h + wrapDeg(h - last.h);
      this.yawRate = Math.max(-90, Math.min(90, (h - last.h) / dt));
      // a jump of more than ~25 m between fixes is a reset (GPS re-acquired, sim restarted): don't
      // draw the boat sliding across the lake, just put it there
      if (Math.hypot(x - last.x, z - last.z) > 25) this.buf.length = 0;
    }
    this.buf.push({ t, x, z, h });
    if (this.buf.length > 24) this.buf.shift();
    if (speed != null) this.speed = speed;
    if (!this.has || this.buf.length === 1) Object.assign(this, { has: true, x, z, h, prevX: x, prevZ: z });
  },
  sample(rt) {
    const B = this.buf, n = B.length;
    if (rt <= B[0].t) return B[0];
    const last = B[n - 1];
    if (rt >= last.t) {
      // ran out of fixes (late packet, lost link): coast along the last motion for at most half a
      // second, then hold still rather than invent a path
      const a = B[n - 2] ?? last, span = Math.max(1e-3, last.t - a.t), ex = Math.min(rt - last.t, 0.5);
      return n < 2 ? last : { x: last.x + ((last.x - a.x) / span) * ex, z: last.z + ((last.z - a.z) / span) * ex, h: last.h + ((last.h - a.h) / span) * ex };
    }
    let i = n - 2;
    while (i > 0 && B[i].t > rt) i--;
    const p0 = B[Math.max(0, i - 1)], p1 = B[i], p2 = B[i + 1], p3 = B[Math.min(n - 1, i + 2)];
    const k = (rt - p1.t) / (p2.t - p1.t);
    // Catmull-Rom through the fixes: passes through every one, with no corners between them
    const cr = (a, b, c, d) => 0.5 * (2 * b + (c - a) * k + (2 * a - 5 * b + 4 * c - d) * k * k + (3 * b - a - 3 * c + d) * k * k * k);
    return { x: cr(p0.x, p1.x, p2.x, p3.x), z: cr(p0.z, p1.z, p2.z, p3.z), h: p1.h + (p2.h - p1.h) * k };
  },
  step(dt, t) {
    if (!this.buf.length) return;
    this.delay = damp(this.delay, Math.max(0.15, Math.min(1.3, this.interval * 1.6)), 1.5, dt);
    const s = this.sample(t - this.delay);
    // a very light final smoothing hides the odd late packet without adding visible lag
    this.x = damp(this.x, s.x, 20, dt);
    this.z = damp(this.z, s.z, 20, dt);
    // heading is eased harder than position: the compass jitters a couple of degrees reading to
    // reading, and a model that twitches five times a second reads as a boat that's fishtailing
    this.h += wrapDeg(s.h - this.h) * (1 - Math.exp(-5 * dt));
    this.vx = damp(this.vx, (this.x - this.prevX) / Math.max(dt, 1e-3), 6, dt);
    this.vz = damp(this.vz, (this.z - this.prevZ) / Math.max(dt, 1e-3), 6, dt);
    this.prevX = this.x; this.prevZ = this.z;
  },
};

// ---------------------------------------------------------------------------------------------
// websocket
// ---------------------------------------------------------------------------------------------
// Two ways to be connected. With a ground station (the real one, or sim/run.py) the page opens
// its WebSocket. On a static host (GitHub Pages, Vercel) there is no station, so the whole
// simulator runs inside the page in a Web Worker (sim/browser/core.py under Pyodide) and talks
// the same messages. The choice is made once, by asking the station for its map.
const api = (path) => new URL('../' + path, location.href).href;
let ws;                   // whatever we're connected to: { readyState, send(), close() }
let local = null;         // the worker, in local mode
async function pickTransport() {
  if (new URLSearchParams(location.search).get('local') === '1') return 'local';
  try {
    const ctl = new AbortController();
    setTimeout(() => ctl.abort(), 3000);
    const r = await fetch(api('api/grid'), { cache: 'no-store', signal: ctl.signal });
    if (r.ok) return 'ws';
  } catch { /* no station answers: run the sim here */ }
  return 'local';
}
function onMessage(m) {
    S.lastMsgAt = now();
    switch (m.t) {
      case 'world': onWorld(m); break;
      case 'tlm': onTlm(m); break;
      case 'trail': trail.add(m.lat, m.lon, m.signal_dbm, now()); break;
      case 'evt': onEvent(m); break;
      case 'ack': onAck(m); break;
      case 'grid': onGrid(m); break;
      case 'link': onLink(m.up, m.ts); break;
      case 'control': setHolder(m.holder); break;
    }
}
async function connect() {
  const mode = await pickTransport();
  if (mode === 'local') return connectLocal();
  const sock = new WebSocket(api('ws').replace(/^http/, 'ws'));
  ws = sock;
  sock.onopen = () => { S.socket = true; ui.setSocket(true); };
  sock.onmessage = (e) => onMessage(JSON.parse(e.data));
  sock.onclose = () => {
    if (S.socket) ui.toast('crit', 'Lost the ground station', 'Reconnecting…', 2500);
    S.socket = false; ui.setSocket(false);
    setTimeout(connect, 1000);
  };
}
function connectLocal() {
  const w = new Worker('js/worker/sim.worker.js');
  local = { worker: w, waiting: [] };
  ws = { readyState: 0, send: (data) => w.postMessage({ type: 'send', data }), close: () => {} };
  ui.toast('info', 'Simulator running in your browser', 'No ground station on this page: the boat, the lake and the station run here, just for you. First load takes a moment.', 9000);
  w.onmessage = (e) => {
    const m = e.data;
    if (m.type === 'status') ui.setLastSeenText(m.text);
    else if (m.type === 'ready') { ws.readyState = 1; S.socket = true; ui.setSocket(true); S.lastMsgAt = now(); }
    else if (m.type === 'msgs') m.list.forEach((s) => onMessage(JSON.parse(s)));
    else if (m.type === 'truth' || m.type === 'csv') { const cb = local.waiting.shift(); cb?.res(m.data); }
    else if (m.type === 'busy') { const cb = local.waiting.shift(); cb?.rej(new Error('sim not ready')); }
    else if (m.type === 'error') { console.error('sim worker:', m.text); ui.toast('crit', 'Simulator error', m.text.slice(0, 120), 8000); }
  };
  w.onerror = (e) => ui.toast('crit', 'Simulator failed to start', e.message || 'see the console', 10000);
  // the page is at .../viewer/; the Python files are published next to it at .../py/
  w.postMessage({ type: 'init', pyBase: new URL('../py/', location.href).href });
  // in local mode the export is produced in the page, and the truth feed is a call, not HTTP
  // a question to the worker; answered in order. Before the sim is ready there is no answer, so
  // give up after 3 s (the truth feed just tries again) instead of waiting forever
  const ask = (type) => new Promise((res, rej) => {
    const entry = { res, rej };
    local.waiting.push(entry);
    w.postMessage({ type });
    setTimeout(() => { const i = local.waiting.indexOf(entry); if (i >= 0) { local.waiting.splice(i, 1); rej(new Error('sim not ready')); } }, 3000);
  });
  localTruth = () => ask('truth').then((s) => JSON.parse(s));
  ui.$('btnExport').addEventListener('click', async (e) => {
    e.preventDefault();
    const csv = await ask('csv');
    const a = document.createElement('a');
    a.href = URL.createObjectURL(new Blob([csv], { type: 'text/csv' })); a.download = 'run.csv'; a.click();
  });
}
let localTruth = null;
const send = (o) => ws && ws.readyState === 1 && ws.send(JSON.stringify(o));
// The station talks several times a second (telemetry, or the grid every 2 s). A socket that
// goes silent without closing (flaky Wi-Fi, a sleeping laptop) would leave stale numbers on
// screen, so after 8 s of nothing it's closed, which triggers the reconnect above.
setInterval(() => {
  if (!local && ws && ws.readyState === 1 && S.lastMsgAt && now() - S.lastMsgAt > 8) { ui.toast('warn', 'Station went quiet', 'Reconnecting…', 2500); ws.close(); }
}, 2000);

function onWorld(w) {
  if (w.you) S.me = w.you;
  setOrigin(w.origin);
  if (drivenFence) { scene.remove(drivenFence); drivenFence.userData.dispose(); }
  if (w.fence_radius_m) {
    // the boat enforces a circle round the station (boat-pi); draw exactly that
    fence = { r: w.fence_radius_m };
    drivenFence = circleFence(w.fence_radius_m, 0x7dd3fc);
  } else {
    const [ax, az] = toXZ(...w.fence_driven[0]), [bx, bz] = toXZ(...w.fence_driven[1]);
    fence = { x0: Math.min(ax, bx), x1: Math.max(ax, bx), z0: Math.min(az, bz), z1: Math.max(az, bz) };
    drivenFence = rectFence(w.fence_driven[0], w.fence_driven[1], 0x7dd3fc, 1.4, 0.6);
  }
  scene.add(drivenFence);
  env.surface.material.uniforms.uRingMax.value = fence.r ?? 150;
  if (sweepFence) { scene.remove(sweepFence); sweepFence.userData.dispose(); sweepFence = null; }
  if (w.sweep_corners) { sweepFence = rectFence(w.sweep_corners[0], w.sweep_corners[1], 0xfbbf24); scene.add(sweepFence); }
  sweep.set(w.sweep_points);
  minimap.setWorld(fence, w.sweep_corners, sweep.points);
  ui.setSweep(0, w.sweep_points?.length ?? 0);
  if (w.holder !== undefined) setHolder(w.holder);
  (w.events || []).forEach((e) => ui.addEvent(e, { animateIn: false }));
  if (w.link_up === false) onLink(false, w.ts, true);
}

function onTlm(m) {
  const t = now();
  S.tlm = m; S.tlmAt = t;
  const [x, z] = toXZ(m.lat, m.lon);
  if (m.gps_fix) est.onFix(x, z, m.heading_deg ?? 0, m.speed_mps, t);
  boat.setMode(m.mode);
  pursuit.set(m.mode !== 'DRIVEN' ? m.target : null, MODE_COLORS[m.mode] ?? 0xffffff);
  if (m.home && (!home.g.visible || home.lat !== m.home[0] || home.lon !== m.home[1])) { home.set(m.home); home.lat = m.home[0]; home.lon = m.home[1]; }
  ui.setMode(m.mode, m.home_phase, m.wp_index, sweep.points.length);
  if (m.mode === 'AUTO' && m.wp_index != null) { sweep.rebuild(m.wp_index); ui.setSweep(m.wp_index, sweep.points.length); }

  let fencePct = null;
  if (fence) {
    if (fence.r) fencePct = (100 * Math.hypot(x, z)) / fence.r;
    else {
      const hx = (fence.x1 - fence.x0) / 2, hz = (fence.z1 - fence.z0) / 2;
      fencePct = 100 * Math.max(Math.abs(x - (fence.x1 + fence.x0) / 2) / hx, Math.abs(z - (fence.z1 + fence.z0) / 2) / hz);
    }
    // ARCHITECTURE.md: the dashboard warns at 80 % of the way to the edge
    if (fencePct >= 80 && !S.fenceWarned) { S.fenceWarned = true; ui.toast('warn', 'Near the fence', `${Math.round(fencePct)} % of the way to the edge.`); }
    if (fencePct < 75) S.fenceWarned = false;
  }
  ui.setTelemetry(m, { distM: Math.hypot(x, z), fencePct });

  if (S.pending && m.mode === S.pending.mode) S.pending = null;
  if (S.link === false && t - S.linkLostAt > 1) onLink(true, m.ts);   // telemetry flowing means the link is back
  ui.setLinkChip(S.link, m.signal_dbm);
  refreshCommand();
}

function onEvent(m) {
  const sev = ui.addEvent(m);
  if (m.kind === 'wp_reached') {
    const i = parseInt(m.detail, 10) - 1;
    const p = sweep.points[i];
    if (p) ripple(p.x, p.z, 0xffffff, 3.5, 1.6, 0.35);
  } else if (m.kind === 'sweep_done') {
    sweep.rebuild(sweep.points.length);
    ui.setSweep(sweep.points.length, sweep.points.length);
    ui.toast('ok', 'Sweep complete', 'The boat is following its trail home.');
  } else if (sev === 'crit' && m.kind !== 'link_lost') {
    ui.toast('crit', ui.eventTitle(m.kind), m.detail || '');
  }
}

function onAck(m) {
  if (m.for === 'mode') {
    const wanted = S.pending?.mode;
    S.pending = null;
    if (!m.ok) {
      ui.addEvent({ kind: 'ack_refused', detail: m.msg, ts: m.ts });
      ui.toast('warn', `Boat refused ${wanted ? ui.MODES[wanted]?.name ?? wanted : 'the request'}`, cap(m.msg));
      const btn = document.querySelector(`.mode-btn[data-mode="${wanted}"]`);
      if (btn) ui.shake(btn);
    }
  } else if (m.ok) {
    ui.addEvent({ kind: 'ack_ok', detail: `waypoints: ${m.msg}`, ts: m.ts });
  } else {
    ui.addEvent({ kind: 'ack_refused', detail: `${m.for}: ${m.msg}`, ts: m.ts });
    if (m.for === 'sweep') { S.pending = null; ui.toast('warn', 'Sweep not started', cap(m.msg)); }
  }
  refreshCommand();
}
const cap = (s) => (s ? s[0].toUpperCase() + s.slice(1) + '.' : '');

const LAYERS = {
  covered: { range: [0, 1], unit: '' },
  ph: { range: [6.5, 8.5], unit: '' },
  temp_c: { range: [18, 24], unit: ' °C' },
  turb_ntu: { range: [5, 30], unit: ' NTU' },
  cond_us: { range: [350, 500], unit: ' µS' },
};
function onGrid(g) {
  S.grid = g;
  coverage.set(g, S.layer, LAYERS[S.layer].range, now());
  trash.sync(g.trash || [], now(), (x, z) => { ripple(x, z, 0xfb923c, 5, 1.2); ripple(x, z, 0xfb923c, 3, 0.9, 0.2); });
  ui.setCoverage(g.coverage_pct);
}

function onLink(up, ts, quiet = false) {
  if (up === S.link) return;
  S.link = up;
  if (!up) S.linkLostAt = now();
  ui.setLinkChip(up, S.tlm?.signal_dbm);
  ui.show(ui.$('banner'), !up);
  ui.setVignette(!up);
  station.led.material.color.set(up ? 0x34d399 : 0xef4444);
  if (!quiet) ui.addEvent({ kind: up ? 'station_link_up' : 'station_link_down', ts: ts ?? Date.now() / 1000 });
  if (up && !quiet) ui.toast('ok', 'Link restored', 'Held events from the boat will follow.');
  refreshCommand();
}

function setHolder(h) {
  const hadIt = S.holder === S.me && S.me != null;
  S.holder = h;
  const mine = h != null && h === S.me;
  ui.$('btnRelease').disabled = !mine;
  if (!mine && hadIt) S.conveyorCmd = false;
  refreshCommand();
}

// ---------------------------------------------------------------------------------------------
// command panel: what each button may do right now, and why not
// ---------------------------------------------------------------------------------------------
function refreshCommand() {
  const mode = S.tlm?.mode;
  const mine = S.holder != null && S.holder === S.me;
  // holding control only means steering while the boat is DRIVEN; in AUTO or COMING_HOME it ignores the stick
  const steering = mine && mode === 'DRIVEN';
  ui.$('ctlState').textContent = steering ? 'You are driving' : mine ? 'You hold control' : S.holder ? 'Someone else has control' : 'Nobody has control';
  ui.$('ctlState').className = 'text-[12px] ' + (mine ? 'text-bone' : 'text-mist/55');
  ui.show(ui.$('driveHud'), steering, 'rise');
  ui.$('hint').classList.toggle('hidden', steering);
  const batt = S.tlm?.batt_pct;
  // mirror the boat's rules (boat-pi/modes.py) so the page can explain a "no" before asking;
  // the boat still decides
  const sweepBlock =
    !S.link ? 'No link to the boat.' :
    mode === 'COMING_HOME' ? 'A sweep starts from Drive: press Drive first, then Sweep.' :
    batt != null && batt <= 30 ? 'Battery at or below 30 %: no new sweeps.' :
    S.tlm && !S.tlm.gps_fix ? 'No GPS fix.' : null;
  for (const b of document.querySelectorAll('.mode-btn')) {
    const want = b.dataset.mode;
    const state = S.pending?.mode === want ? 'pending' : want === mode ? 'active' : 'idle';
    b.dataset.state = state;
    b.setAttribute('aria-pressed', String(want === mode));
    b.disabled = !S.socket || (want === 'AUTO' && !!sweepBlock && state !== 'active') || (!S.link && want !== 'COMING_HOME');
  }
  let hint;
  if (!S.socket) hint = 'Not connected to the ground station.';
  else if (!S.link) hint = 'No link: the boat cannot hear requests. It is bringing itself back.';
  else if (S.pick) hint = 'Drawing a sweep area on the water…';
  else if (S.pending) hint = `Asked for ${ui.MODES[S.pending.mode]?.name ?? S.pending.mode}. Waiting for the boat to answer…`;
  else if (mode === 'COMING_HOME') hint = 'Coming home on its own. Press Drive to take over; a sweep can only start from Drive.';
  else if (mode === 'AUTO') hint = 'Sweeping the area. Drive takes the wheel back; Home follows the trail home.';
  else if (mode === 'DRIVEN' && mine) hint = 'You are driving. W A S D or a gamepad; C toggles the conveyor.';
  else if (mode === 'DRIVEN') hint = 'Press Drive to take the wheel, or Sweep to draw an area.';
  else hint = 'Waiting for the first telemetry from the boat.';
  if (sweepBlock && mode === 'DRIVEN' && S.link && !S.pending && !S.pick) hint += ` Sweep unavailable: ${sweepBlock.toLowerCase()}`;
  ui.$('modeHint').textContent = hint;
}

function ask(mode) {
  S.pending = { mode, at: now() };
  refreshCommand();
}

for (const b of document.querySelectorAll('.mode-btn')) {
  b.addEventListener('click', () => {
    const want = b.dataset.mode;
    if (want === 'DRIVEN') {
      // Take control: the station hands us the wheel and asks the boat for DRIVEN
      send({ t: 'take' });
      if (S.tlm?.mode !== 'DRIVEN') ask('DRIVEN');
    } else if (want === 'AUTO') {
      if (S.pick) cancelPick(); else startPick();
    } else if (want === 'COMING_HOME') {
      send({ t: 'home' });
      if (S.tlm?.mode !== 'COMING_HOME') ask('COMING_HOME');
    }
  });
}
ui.$('btnRelease').onclick = () => send({ t: 'release' });
ui.$('btnTrash').onclick = () => {
  if (!S.tlm) return;
  send({ t: 'trash' });
};

// ---------------------------------------------------------------------------------------------
// sweep picking: two clicks on the water, with a live preview of the rectangle
// ---------------------------------------------------------------------------------------------
const plane = new THREE.Plane(new THREE.Vector3(0, 1, 0), 0);
const ray = new THREE.Raycaster();
const ndc = new THREE.Vector2();
const previewGeo = new LineGeometry().setPositions(new Array(15).fill(0));
const preview = new Line2(previewGeo, lineMat(0xfbbf24, 2, { dashed: true, dashSize: 1, gapSize: 0.6 }));
preview.visible = false;
preview.renderOrder = 6;
scene.add(preview);

function waterPoint(e) {
  const r = canvas.getBoundingClientRect();
  ndc.set(((e.clientX - r.left) / r.width) * 2 - 1, -((e.clientY - r.top) / r.height) * 2 + 1);
  ray.setFromCamera(ndc, camera);
  return ray.ray.intersectPlane(plane, new THREE.Vector3());
}
function startPick() {
  S.pick = 1; S.corner1 = null;
  ui.$('pickText').textContent = 'Click the first corner of the sweep area on the water';
  ui.$('pickDims').textContent = '';
  ui.show(ui.$('pickHint'), true);
  canvas.style.cursor = 'crosshair';
  refreshCommand();
}
function cancelPick() {
  S.pick = 0; S.corner1 = null;
  preview.visible = false;
  ui.show(ui.$('pickHint'), false);
  canvas.style.cursor = '';
  refreshCommand();
}
ui.$('pickCancel').onclick = cancelPick;

let downAt = null;
canvas.addEventListener('pointerdown', (e) => { downAt = [e.clientX, e.clientY]; });
canvas.addEventListener('pointermove', (e) => {
  if (S.pick !== 2 || !S.corner1) return;
  const p = waterPoint(e); if (!p) return;
  const a = S.corner1;
  previewGeo.setPositions([a.x, 0.12, a.z, p.x, 0.12, a.z, p.x, 0.12, p.z, a.x, 0.12, p.z, a.x, 0.12, a.z]);
  preview.computeLineDistances();
  preview.visible = true;
  ui.$('pickDims').textContent = `${Math.abs(p.x - a.x).toFixed(0)} × ${Math.abs(p.z - a.z).toFixed(0)} m`;
});
canvas.addEventListener('pointerup', (e) => {
  // a drag is the camera orbiting, not a click
  if (!S.pick || !downAt || Math.hypot(e.clientX - downAt[0], e.clientY - downAt[1]) > 6) return;
  const p = waterPoint(e); if (!p) return;
  if (S.pick === 1) {
    S.corner1 = p; S.pick = 2;
    ripple(p.x, p.z, 0xfbbf24, 2.5, 0.7);
    ui.$('pickText').textContent = 'Now click the opposite corner';
    return;
  }
  const a = S.corner1;
  if (Math.abs(p.x - a.x) < 6 || Math.abs(p.z - a.z) < 6) {
    ui.toast('warn', 'Sweep area too small', 'Make it at least 6 m on each side; the planner keeps 2 m from every edge.');
    return;
  }
  ripple(p.x, p.z, 0xfbbf24, 2.5, 0.7);
  send({ t: 'sweep', corners: [toLatLon(a.x, a.z), toLatLon(p.x, p.z)] });
  ask('AUTO');
  cancelPick();
});

// ---------------------------------------------------------------------------------------------
// driving: keyboard or gamepad -> `ctl` at 10 Hz, only while we hold control.
// A key going down or up also sends at once: a slow laptop can delay the 10 Hz timer by a few
// hundred ms, and letting go of W should stop the boat now, not on the next tick.
// ---------------------------------------------------------------------------------------------
const keys = {};
const drive = { th: 0, st: 0 };
const DRIVE_KEYS = new Set(['w', 'a', 's', 'd', 'arrowup', 'arrowdown', 'arrowleft', 'arrowright']);
addEventListener('keydown', (e) => {
  if (e.metaKey || e.ctrlKey || e.altKey) return;
  const k = e.key.toLowerCase();
  const was = keys[k];
  keys[k] = true;
  if (DRIVE_KEYS.has(k) && !was) sendCtl();
  if (k === 'escape' && S.pick) cancelPick();
  if (k === 'c' && S.holder === S.me && !e.repeat) setConveyor(!S.conveyorCmd);
  if (k === '1') setCam('follow');
  if (k === '2') setCam('orbit');
  if (k === '3') setCam('top');
});
addEventListener('keyup', (e) => {
  const k = e.key.toLowerCase();
  keys[k] = false;
  if (DRIVE_KEYS.has(k)) sendCtl();
});
addEventListener('blur', () => { for (const k in keys) keys[k] = false; sendCtl(); });   // never leave a key "stuck" on

function setConveyor(on) {
  S.conveyorCmd = on;
  sendCtl();
  ui.$('btnConv').setAttribute('aria-pressed', String(on));
  const el = ui.$('hudConv');
  el.textContent = on ? 'on' : 'off';
  el.className = 'ml-1 ' + (on ? 'text-emerald-200' : 'text-mist/50');
}

// the on-screen stick: drag within the pad, let go to stop (safe default for a phone in a pocket)
const joy = { active: false, th: 0, st: 0, id: null };
const joyEl = ui.$('joy'), stickEl = ui.$('stick');
function joyFrom(e) {
  const r = joyEl.getBoundingClientRect();
  const R = r.width / 2 - 10;
  let dx = (e.clientX - (r.left + r.width / 2)) / R, dy = (e.clientY - (r.top + r.height / 2)) / R;
  const m = Math.hypot(dx, dy);
  if (m > 1) { dx /= m; dy /= m; }
  const dz = (v) => (Math.abs(v) < 0.08 ? 0 : v);
  joy.th = dz(-dy); joy.st = dz(dx);
}
joyEl.addEventListener('pointerdown', (e) => { joy.active = true; joy.id = e.pointerId; joyEl.setPointerCapture(e.pointerId); joyFrom(e); sendCtl(); e.preventDefault(); });
joyEl.addEventListener('pointermove', (e) => { if (joy.active && e.pointerId === joy.id) { joyFrom(e); } });
const joyEnd = (e) => { if (joy.active && e.pointerId === joy.id) { joy.active = false; joy.th = joy.st = 0; sendCtl(); } };
joyEl.addEventListener('pointerup', joyEnd);
joyEl.addEventListener('pointercancel', joyEnd);
ui.$('btnConv').onclick = () => setConveyor(!S.conveyorCmd);
ui.$('btnReleaseHud').onclick = () => send({ t: 'release' });

let padWasDown = [false, false];
setInterval(sendCtl, 100);
function sendCtl() {
  if (S.holder == null || S.holder !== S.me) return;
  let th = (keys.w || keys.arrowup ? 1 : 0) - (keys.s || keys.arrowdown ? 1 : 0);
  let st = (keys.d || keys.arrowright ? 1 : 0) - (keys.a || keys.arrowleft ? 1 : 0);
  if (joy.active) { th = joy.th; st = joy.st; }
  const gp = navigator.getGamepads?.()[0];
  ui.$('padChip').classList.toggle('hidden', !gp);
  ui.$('padChip').classList.toggle('inline-flex', !!gp);
  if (gp) {
    const dz = (v) => (Math.abs(v) < 0.08 ? 0 : v);
    const gth = dz(-gp.axes[1]), gst = dz(gp.axes[2] ?? gp.axes[0]);
    if (gth || gst) { th = gth; st = gst; }
    // A turns the conveyor on, B off; act on the press, not every poll while held
    const a = !!gp.buttons[0]?.pressed, b = !!gp.buttons[1]?.pressed;
    if (a && !padWasDown[0]) setConveyor(true);
    if (b && !padWasDown[1]) setConveyor(false);
    padWasDown = [a, b];
  }
  drive.th = th * 0.8; drive.st = st * 0.6;
  send({ t: 'ctl', throttle: drive.th, steer: drive.st, conveyor: S.conveyorCmd });
  ui.$('hudTh').textContent = (drive.th >= 0 ? ' ' : '') + drive.th.toFixed(2);
  ui.$('hudSt').textContent = (drive.st >= 0 ? ' ' : '') + drive.st.toFixed(2);
  // the stick shows whatever is driving: thumb, keys or gamepad
  const R = joyEl.clientWidth / 2 - 10;
  stickEl.style.transform = `translate(calc(-50% + ${(st * R).toFixed(1)}px), calc(-50% + ${(-th * R).toFixed(1)}px))`;
  joyEl.setAttribute('aria-valuetext', th || st ? `throttle ${drive.th.toFixed(2)}, steer ${drive.st.toFixed(2)}` : 'stopped');
}

// ---------------------------------------------------------------------------------------------
// camera
// ---------------------------------------------------------------------------------------------
let camAnim = null;
function setCam(mode) {
  S.camMode = mode;
  for (const b of document.querySelectorAll('[data-cam]')) b.setAttribute('aria-pressed', String(b.dataset.cam === mode));
  controls.minPolarAngle = 0;
  controls.maxPolarAngle = THREE.MathUtils.degToRad(86);
  const fromP = camera.position.clone(), fromT = controls.target.clone();
  let toP, toT;
  if (mode === 'top') {
    // frame the station and the boat (and the sweep, if there is one)
    const box = new THREE.Box3().expandByPoint(new THREE.Vector3(0, 0, 0)).expandByPoint(new THREE.Vector3(est.x, 0, est.z));
    sweep.points.forEach((p) => box.expandByPoint(p));
    const c = box.getCenter(new THREE.Vector3());
    const size = box.getSize(new THREE.Vector3());
    const h = Math.max(40, Math.max(size.x / camera.aspect, size.z) * 1.25 / (2 * Math.tan(THREE.MathUtils.degToRad(camera.fov / 2))));
    toT = c; toP = new THREE.Vector3(c.x, h, c.z + 0.001);
    controls.maxPolarAngle = 0.0001;
  } else if (mode === 'follow') {
    toT = new THREE.Vector3(est.x, 0, est.z);
    const r = THREE.MathUtils.degToRad(est.h);
    toP = toT.clone().add(new THREE.Vector3(-Math.sin(r) * 11 + 5, 6.5, Math.cos(r) * 11));
  } else return;
  camAnim?.stop();
  if (reduceMotion) { camera.position.copy(toP); controls.target.copy(toT); return; }
  camAnim = animate(0, 1, {
    duration: 1.1, ease: [0.65, 0, 0.35, 1],
    onUpdate: (k) => { camera.position.lerpVectors(fromP, toP, k); controls.target.lerpVectors(fromT, toT, k); },
    onComplete: () => { camAnim = null; },
  });
}
for (const b of document.querySelectorAll('[data-cam]')) b.onclick = () => setCam(b.dataset.cam);

// the chart: Area / Boat zoom, and click to look somewhere
for (const b of document.querySelectorAll('[data-chart]')) b.onclick = () => {
  minimap.view = b.dataset.chart;
  for (const o of document.querySelectorAll('[data-chart]')) o.setAttribute('aria-pressed', String(o === b));
};
minimap.onPick = (x, z) => {
  setCam('orbit');
  camAnim?.stop();
  const fromT = controls.target.clone(), fromP = camera.position.clone();
  const toT = new THREE.Vector3(x, 0, z), toP = fromP.clone().add(toT.clone().sub(fromT));
  camAnim = animate(0, 1, { duration: reduceMotion ? 0 : 0.9, ease: [0.65, 0, 0.35, 1],
    onUpdate: (k) => { controls.target.lerpVectors(fromT, toT, k); camera.position.lerpVectors(fromP, toP, k); },
    onComplete: () => { camAnim = null; } });
};
controls.addEventListener('start', () => { camAnim?.stop(); camAnim = null; });

for (const b of document.querySelectorAll('[data-layer]')) b.onclick = () => {
  S.layer = b.dataset.layer;
  for (const o of document.querySelectorAll('[data-layer]')) o.setAttribute('aria-pressed', String(o === b));
  coverage.recolor(S.layer, LAYERS[S.layer].range);
  ui.setLegend(S.layer, LAYERS[S.layer].range, LAYERS[S.layer].unit, RAMP_CSS);
};

// phone: the rails open as sheets
for (const b of document.querySelectorAll('[data-sheet]')) b.onclick = () => {
  for (const o of document.querySelectorAll('[data-sheet]')) o.setAttribute('aria-pressed', String(o === b));
  for (const id of ['railL', 'railR']) {
    const el = ui.$(id);
    const open = b.dataset.sheet === id;
    el.toggleAttribute('data-open', open);
    if (open && !reduceMotion) animate(el, { opacity: [0, 1], y: [16, 0] }, { duration: 0.3, ease: [0.22, 1, 0.36, 1] });
  }
};

// ---------------------------------------------------------------------------------------------
// effects
// ---------------------------------------------------------------------------------------------
const V = (x, y, z) => ({ x, y, z });
function ripple(x, z, color, radius, dur, alpha = 0.55, y = 0.05) {
  rings.emit(V(x, y, z), V(0, 0, 0), { life: dur, size: 0.2, grow: (radius * 2) / 0.2, color, alpha, width: 0.09 });
}

const rates = { wl: new Rate(), wr: new Rate(), bow: new Rate(), center: new Rate(), drip: new Rate(), intake: new Rate(), mist: new Rate() };
const _v = new THREE.Vector3();
const world = (anchor, m) => _v.copy(anchor).applyMatrix4(m);
const jit = (s) => (Math.random() - 0.5) * s;
let nextPulse = 0;

function emitEffects(dt, t) {
  if (!est.has) return;
  const yaw = THREE.MathUtils.degToRad(est.h);
  const fx = Math.sin(yaw), fz = -Math.cos(yaw);          // forward on the water
  const rx = Math.cos(yaw), rz = Math.sin(yaw);           // to starboard
  const speed = Math.hypot(est.vx, est.vz);
  const A = boat.anchors;
  boat.root.updateMatrixWorld();
  const M = boat.root.matrixWorld, H = boat.hull.matrixWorld;

  // prop wash: one stream per thruster, as strong as that motor is being told to push
  for (const [side, m, rate] of [[A.thrusterL, est.left, rates.wl], [A.thrusterR, est.right, rates.wr]]) {
    const n = rate.take(70 * Math.abs(m), dt);
    for (let i = 0; i < n; i++) {
      const p = world(side, M);
      const push = -(0.5 + 1.8 * Math.abs(m)) * Math.sign(m);
      foam.emit(V(p.x + jit(0.08), 0.03, p.z + jit(0.08)),
        V(fx * push + est.vx * 0.25 + rx * jit(0.9), 0, fz * push + est.vz * 0.25 + rz * jit(0.9)),
        { life: 0.8 + Math.random() * 0.9, size: 0.08 + Math.random() * 0.06, grow: 3.2, color: 0xf2f8fa, alpha: 0.32, drag: 2.6 });
      if (Math.abs(m) > 0.55 && Math.random() < 0.3) {
        spray.emit(V(p.x, 0.04, p.z), V(fx * push * 0.4 + jit(0.4), 0.6 + Math.random() * 0.7, fz * push * 0.4 + jit(0.4)),
          { life: 0.55, size: 0.035, color: 0xe2f1f6, alpha: 0.7, gravity: 9.8 });
      }
    }
  }

  // hull wake: each bow pushes water out to its side; together they draw the V behind the boat
  if (speed > 0.12) {
    const k = Math.min(1, speed / 0.9);
    const n = rates.bow.take(55 * speed, dt);
    for (let i = 0; i < n; i++) for (const [bow, s] of [[A.bowL, -1], [A.bowR, 1]]) {
      const p = world(bow, M);
      const out = 0.22 + 0.4 * speed;
      foam.emit(V(p.x + jit(0.05), 0.025, p.z + jit(0.05)),
        V(rx * s * out - fx * 0.08 * speed, 0, rz * s * out - fz * 0.08 * speed),
        { life: 3.2 + Math.random() * 2.0, size: 0.09, grow: 3.4, color: 0xf3f8fa, alpha: 0.42 * k, drag: 0.6 });
    }
    // and a long, faint streak of disturbed water straight behind
    const c = rates.center.take(28 * speed, dt);
    for (let i = 0; i < c; i++) {
      foam.emit(V(est.x - fx * 0.7 + rx * jit(0.5), 0.02, est.z - fz * 0.7 + rz * jit(0.5)),
        V(-fx * 0.12 + jit(0.06), 0, -fz * 0.12 + jit(0.06)),
        { life: 5 + Math.random() * 3, size: 0.26, grow: 2.4, color: 0xe6eff3, alpha: 0.14 * k, drag: 0.3 });
    }
    // a little spray off the bows when it's really moving
    const s = rates.mist.take(Math.max(0, speed - 0.7) * 30, dt);
    for (let i = 0; i < s; i++) {
      const p = world(Math.random() < 0.5 ? A.bowL : A.bowR, M);
      spray.emit(V(p.x, 0.05, p.z), V(fx * speed * 0.6 + jit(0.4), 0.5 + Math.random() * 0.5, fz * speed * 0.6 + jit(0.4)),
        { life: 0.5, size: 0.03, color: 0xe6f3f8, alpha: 0.6, gravity: 9.8 });
    }
  }

  // conveyor: water dripping off the belt top into the basket, and a stir at the intake
  if (est.conveyor > 0.5) {
    const n = rates.drip.take(26, dt);
    for (let i = 0; i < n; i++) {
      const p = world(_tmp.copy(A.beltTop).add(_tmp2.set(jit(0.3), 0, 0)), H);
      spray.emit(V(p.x, p.y, p.z), V(-fx * 0.25 + jit(0.15), 0.12, -fz * 0.25 + jit(0.15)),
        { life: 0.42, size: 0.022, color: 0xcfe8f3, alpha: 0.75, gravity: 9.8 });
    }
    const m = rates.intake.take(16, dt);
    for (let i = 0; i < m; i++) {
      const p = world(A.intake, M);
      const a = Math.random() * Math.PI * 2;
      foam.emit(V(p.x + fx * 0.25 + Math.cos(a) * 0.3, 0.03, p.z + fz * 0.25 + Math.sin(a) * 0.3),
        V(-Math.cos(a) * 0.25 - fx * 0.1, 0, -Math.sin(a) * 0.25 - fz * 0.1),
        { life: 1.1, size: 0.09, grow: 1.6, color: 0xeef6f8, alpha: 0.4, drag: 1 });
    }
  }

  // while lost, the last known position pulses red
  if (!S.link && t > nextPulse) { nextPulse = t + 1.4; ripple(est.x, est.z, 0xef4444, 5, 1.3, 0.6); }
}
const _tmp = new THREE.Vector3(), _tmp2 = new THREE.Vector3(), _belt = new THREE.Vector3();

// ---------------------------------------------------------------------------------------------
// frame loop
// ---------------------------------------------------------------------------------------------
function resize() {
  const w = innerWidth, h = innerHeight;
  renderer.setSize(w, h, false);
  env.surface.resize(w * renderer.getPixelRatio(), h * renderer.getPixelRatio());
  labels.setSize(w, h);
  camera.aspect = w / h;
  camera.updateProjectionMatrix();
}
addEventListener('resize', resize);
resize();

// On a slow GPU every frame takes long, and the page (including the 10 Hz drive loop) suffers.
// Watch the frame time and render fewer pixels until it's smooth again; go back up when it is.
const small = Math.min(innerWidth, innerHeight) < 700;      // a phone or a small tablet: start lighter
const quality = { max: Math.min(small ? 1.5 : 2, devicePixelRatio), ratio: Math.min(small ? 1.25 : 2, devicePixelRatio), ft: 1 / 60, checkAt: 3 };
renderer.setPixelRatio(quality.ratio);
function adaptQuality(rawDt, t) {
  quality.ft += (rawDt - quality.ft) * 0.05;
  if (t < quality.checkAt) return;
  let next = quality.ratio;
  if (quality.ft > 1 / 30 && quality.ratio > 0.6) next = Math.max(0.6, quality.ratio * 0.75);
  else if (quality.ft < 1 / 75 && quality.ratio < quality.max) next = Math.min(quality.max, quality.ratio / 0.75);
  if (next !== quality.ratio) {
    quality.ratio = next;
    renderer.setPixelRatio(next);
    resize();
    quality.checkAt = t + 2.5;          // let it settle before judging again
  } else quality.checkAt = t + 0.5;
}

let last = now();
let pitch = 0, roll = 0, heave = 0, prevSpeed = 0;
function frame() {
  const t = now();
  adaptQuality(t - last, t);
  const dt = Math.min(0.1, t - last);
  last = t;

  est.step(dt, t);
  const m = S.tlm;
  const lostNow = !S.link || (m && t - S.tlmAt > 4);
  est.left = damp(est.left, lostNow ? 0 : m?.left ?? 0, 4, dt);
  est.right = damp(est.right, lostNow ? 0 : m?.right ?? 0, 4, dt);
  est.conveyor = damp(est.conveyor, m?.conveyor && !lostNow ? 1 : 0, 3, dt);
  est.lost = damp(est.lost, lostNow ? 1 : 0, 2.5, dt);

  // boat pose: position and heading from the estimator, the rest from the water under it
  boat.root.position.set(est.x, 0, est.z);
  boat.root.rotation.y = headingToYaw(est.h);
  const yaw = THREE.MathUtils.degToRad(est.h);
  const [sx, sz] = waveSlope(est.x, est.z, t);
  const along = sx * Math.sin(yaw) - sz * Math.cos(yaw);
  const across = sx * Math.cos(yaw) + sz * Math.sin(yaw);
  const speed = Math.hypot(est.vx, est.vz);
  const accel = (speed - prevSpeed) / Math.max(dt, 1e-3); prevSpeed = speed;
  heave = damp(heave, waveHeight(est.x, est.z, t) - 0.015 * speed, 6, dt);
  pitch = damp(pitch, Math.atan(along) * 1.6 + 0.012 * speed - 0.02 * Math.max(-1, Math.min(1, accel)), 5, dt);
  roll = damp(roll, Math.atan(across) * 1.6 + est.yawRate * speed * 0.0006, 5, dt);
  boat.hull.position.y = heave;
  boat.hull.rotation.set(pitch, 0, roll);
  boat.update(dt, t, est.conveyor, est.lost);

  // the label only appears once the real-size boat is too small to see
  const camD = camera.position.distanceTo(boat.root.position);
  const lbl = boatLabel.element;
  lbl.style.opacity = String(Math.max(0, Math.min(1, (camD - 28) / 20)));
  if (m) {
    const col = lostNow ? '#f87171' : ui.MODES[m.mode]?.hex ?? '#94a3b8';
    const text = lostNow ? 'Last known' : `${ui.MODES[m.mode]?.name ?? ''} · ${(m.speed_mps ?? 0).toFixed(1)} m/s`;
    if (lbl.dataset.text !== text) { lbl.innerHTML = `<span class="dot" style="background:${col}"></span>${text}`; lbl.dataset.text = text; }
  }

  // camera follow: carry the camera along with the boat so the user's chosen angle is kept
  if (S.camMode === 'follow' && est.has && !camAnim) {
    const before = controls.target.clone();
    controls.target.x = damp(controls.target.x, est.x, 4, dt);
    controls.target.z = damp(controls.target.z, est.z, 4, dt);
    camera.position.add(controls.target.clone().sub(before));
  }
  controls.update();

  emitEffects(dt, t);
  for (const p of [foam, spray, rings]) p.update(t);
  env.surface.material.uniforms.uTime.value = t;
  env.surface.material.uniforms.uBoat.value.set(est.x, est.z, yaw);
  env.sky.material.uniforms.time.value = t;          // clouds drift
  trail.update(t, est.has ? boat.root.position : null);
  sweep.update(t, m?.mode === 'AUTO' && !lostNow, (x, z) => waveHeight(x, z, t));
  pursuit.update(dt, boat.root.position, !lostNow && m?.mode !== 'DRIVEN');
  minimap.draw(t, { boat: est.has ? { x: est.x, z: est.z, h: est.h } : null, trail: trail.pts, trailCols: trail.cols, target: pursuit.has && m?.mode !== 'DRIVEN' ? pursuit.pos : null, trash: trash.items, flotsam: flotsam.floating(), home: home.g.visible ? home : null, sweepIndex: sweep.index, mode: m?.mode, lost: lostNow, fencePct: null });
  coverage.update(t);
  trash.update(t, (x, z) => waveHeight(x, z, t));
  home.update(t, (x, z) => waveHeight(x, z, t));
  boat.hull.updateMatrixWorld();
  flotsam.update(dt, t, (x, z) => waveHeight(x, z, t), _belt.copy(boat.anchors.beltTop).applyMatrix4(boat.hull.matrixWorld), camera.position);
  station.led.visible = !S.link || (t % 1) < 0.12;     // heartbeat blink; steady red when lost
  ui.setHeadingVisual(est.h);
  ui.setLastSeen(m ? t - S.tlmAt : null, est.buf.length > 3 ? 1 / est.interval : null);
  if (!S.link) ui.$('bannerTime').textContent = `${Math.floor(t - S.linkLostAt)} s`;
  if (S.pending && t - S.pending.at > 6) { S.pending = null; refreshCommand(); }

  renderer.render(scene, camera);
  labels.render(scene, camera);
  requestAnimationFrame(frame);
}

// handle for tests and debugging in the browser console (read-only use, please)
window.__view = { camera, controls, est, S };

ui.intro();
refreshCommand();
connect().then(startTruth);
// start in follow once the boat shows up
const waitFirst = setInterval(() => { if (est.has) { clearInterval(waitFirst); setCam('follow'); } }, 200);
frame();
