// The panels around the 3D view. Plain DOM; Motion (motion.dev, vendored as window.Motion) for
// the few things that should move: panels entering, events arriving, toasts, the link banner.

const { animate, stagger } = window.Motion;
const reduce = matchMedia('(prefers-reduced-motion: reduce)').matches;
const EASE = [0.22, 1, 0.36, 1];
export const $ = (id) => document.getElementById(id);
const fmt = (v, d = 1) => (v == null || Number.isNaN(v) ? '--' : v.toFixed(d));

export const MODES = {
  DRIVEN: { name: 'Driven', css: 'var(--color-driven)', hex: '#8fd3ff' },
  AUTO: { name: 'Auto', css: 'var(--color-auto)', hex: '#f2c66d' },
  COMING_HOME: { name: 'Coming home', css: 'var(--color-home)', hex: '#c4b1ff' },
};
const PHASES = {
  DIRECT: 'straight home',
  WAIT: 'stopped, waiting for signal',
  BACKUP: 'backing up to good signal',
  HOME: 'following the trail home',
  FENCE: 'returning inside the fence',
  DONE: 'stopped at home',
};
const modeWord = (m) => MODES[m]?.name ?? m;

export function intro() {
  if (reduce) return;
  animate('[data-enter]', { opacity: [0, 1], y: [10, 0] }, { delay: stagger(0.035, { startDelay: 0.1 }), duration: 0.6, ease: EASE });
}

// ---------------------------------------------------------------------------------------------
// header: mode pill and status chips
// ---------------------------------------------------------------------------------------------
let shownMode = null;
export function setMode(mode, phase, wp, nWps) {
  const pill = $('modePill');
  const m = MODES[mode];
  pill.style.setProperty('--mc', m ? m.css : 'var(--color-idle)');
  $('modeName').textContent = m ? m.name : 'Waiting for boat';
  let sub = '';
  if (mode === 'COMING_HOME' && phase) sub = PHASES[phase] ?? phase.toLowerCase();
  else if (mode === 'AUTO' && wp != null) sub = nWps ? `waypoint ${Math.min(wp + 1, nWps)} of ${nWps}` : `waypoint ${wp + 1}`;
  $('modeSub').textContent = sub;
  if (mode !== shownMode && shownMode !== null && !reduce) {
    animate(pill, { scale: [0.96, 1] }, { type: 'spring', stiffness: 500, damping: 22 });
    animate('#modePing', { scale: [1, 2.6], opacity: [0.7, 0] }, { duration: 0.9, ease: 'easeOut' });
  }
  shownMode = mode;
}

const DOT = { ok: 'bg-emerald-400', warn: 'bg-amber-400', crit: 'bg-red-400', off: 'bg-slate-500' };
function setDot(id, tone) {
  const el = $(id);
  el.className = 'dot ' + DOT[tone];
}
export function setSocket(up) { setDot('chipWsDot', up ? 'ok' : 'crit'); }
export function setLinkChip(up, dbm) {
  setDot('chipLinkDot', up ? (dbm != null && dbm < -80 ? 'warn' : 'ok') : 'crit');
  $('chipLink').textContent = up ? 'Boat link' : 'Link lost';
}
export function setGps(fix, sats) {
  setDot('chipGpsDot', fix ? (sats >= 6 ? 'ok' : 'warn') : 'crit');
  $('chipGps').textContent = fix ? `GPS ${sats}` : 'No fix';
}

// ---------------------------------------------------------------------------------------------
// compass
// ---------------------------------------------------------------------------------------------
{
  const g = $('compassTicks');
  let s = '';
  for (let a = 0; a < 360; a += 10) {
    const major = a % 30 === 0;
    const r0 = major ? 39 : 42, r1 = 46;
    const t = (a * Math.PI) / 180;
    s += `<line x1="${Math.sin(t) * r0}" y1="${-Math.cos(t) * r0}" x2="${Math.sin(t) * r1}" y2="${-Math.cos(t) * r1}" ${major ? 'stroke="rgb(255 255 255 / 0.5)"' : ''}/>`;
  }
  g.innerHTML = s;
}
// called every frame with the smoothed heading, so the card turns continuously
export function setHeadingVisual(deg) {
  $('compassCard').setAttribute('transform', `rotate(${-deg})`);
}

// ---------------------------------------------------------------------------------------------
// sparklines
// ---------------------------------------------------------------------------------------------
function spark(svg, values, { min, max, minSpan = 1, color, threshold }) {
  const W = 100, H = 40;
  if (values.length < 2) { svg.innerHTML = ''; return; }
  let lo = min ?? Math.min(...values), hi = max ?? Math.max(...values);
  // never zoom in further than minSpan, or sensor noise gets drawn as a cliff
  if (hi - lo < minSpan) { const mid = (hi + lo) / 2; lo = mid - minSpan / 2; hi = mid + minSpan / 2; }
  const span = hi - lo;
  const n = 120;                                      // fixed time window: new samples enter on the right
  const pts = values.map((v, i) => [W - ((values.length - 1 - i) / (n - 1)) * W, H - 3 - ((v - lo) / span) * (H - 6)]);
  const d = pts.map(([x, y], i) => `${i ? 'L' : 'M'}${x.toFixed(2)} ${y.toFixed(2)}`).join('');
  const area = `${d}L${pts.at(-1)[0]} ${H}L${pts[0][0]} ${H}Z`;
  const ty = threshold != null ? H - 3 - ((threshold - lo) / span) * (H - 6) : null;
  const id = svg.id + 'g';
  void area; void id;
  svg.innerHTML = `
    ${ty != null ? `<line x1="0" x2="100" y1="${ty}" y2="${ty}" stroke="rgb(243 239 231 / 0.2)" stroke-dasharray="2 2" vector-effect="non-scaling-stroke"/>` : ''}
    <path d="${d}" fill="none" stroke="${color}" stroke-width="1.2" vector-effect="non-scaling-stroke" stroke-linejoin="round" opacity="0.9"/>`;
}

const hist = { sig: [], temp_c: [], ph: [], turb_ntu: [], cond_us: [] };
const push = (arr, v) => { if (v != null) { arr.push(v); if (arr.length > 120) arr.shift(); } };

const WATER = [
  { key: 'temp_c', name: 'Temperature', unit: '°C', d: 1, span: 1, color: '#f3efe7' },
  { key: 'ph', name: 'pH', unit: '', d: 2, span: 0.3, color: '#f3efe7' },
  { key: 'turb_ntu', name: 'Turbidity', unit: 'NTU', d: 1, span: 4, color: '#f3efe7' },
  { key: 'cond_us', name: 'Conductivity', unit: 'µS/cm', d: 0, span: 20, color: '#f3efe7' },
];
$('water').innerHTML = WATER.map((w) => `
  <div class="min-w-0">
    <div class="label">${w.name}</div>
    <div class="mt-0.5 flex items-baseline gap-1"><span id="w_${w.key}" class="mid">--</span><span class="unit">${w.unit}</span></div>
    <svg id="ws_${w.key}" class="mt-1.5 h-6 w-full" preserveAspectRatio="none" viewBox="0 0 100 40"></svg>
  </div>`).join('');

// ---------------------------------------------------------------------------------------------
// telemetry -> numbers
// ---------------------------------------------------------------------------------------------
export function setTelemetry(m, { distM, fencePct }) {
  $('hdg').textContent = m.heading_deg == null ? '---' : String(Math.round(m.heading_deg) % 360).padStart(3, '0');
  $('spd').textContent = fmt(m.speed_mps, 2);
  $('dist').textContent = fmt(distM, 0);

  const pct = m.batt_pct;
  $('batt').textContent = fmt(pct, 0);
  $('battV').textContent = m.batt_v == null ? '-- V' : m.batt_v.toFixed(2) + ' V';
  const bar = $('battBar');
  bar.style.width = `${Math.max(0, Math.min(100, pct ?? 0))}%`;
  bar.className = pct == null ? 'bg-slate-500' : pct <= 20 ? 'bg-red-400' : pct <= 30 ? 'bg-amber-400' : 'bg-emerald-400';

  const s = m.signal_dbm;
  $('sig').textContent = fmt(s, 0);
  const q = s == null ? ['', ''] : s > -65 ? ['strong', 'text-emerald-200'] : s > -75 ? ['good', 'text-lime-200'] : s > -85 ? ['weak', 'text-amber-200'] : ['failing', 'text-red-300'];
  $('sigQ').textContent = q[0];
  $('sigQ').className = 'ml-1 text-[12px] ' + q[1];
  push(hist.sig, s);
  spark($('sigSpark'), hist.sig, { min: -95, max: -35, color: s != null && s < -80 ? '#fdba74' : '#f3efe7', threshold: -75 });

  for (const w of WATER) {
    const v = m.water?.[w.key];
    $('w_' + w.key).textContent = fmt(v, w.d);
    push(hist[w.key], v);
    spark($('ws_' + w.key), hist[w.key], { color: w.color, minSpan: w.span });
  }

  for (const [side, v] of [['L', m.left], ['R', m.right]]) {
    const el = $('mot' + side);
    const x = Math.max(-1, Math.min(1, v ?? 0));
    el.style.left = x >= 0 ? '50%' : `${50 + x * 50}%`;
    el.style.width = `${Math.abs(x) * 50}%`;
    el.style.transition = reduce ? 'none' : 'left 300ms, width 300ms';
    $('mot' + side + 'v').textContent = (x >= 0 ? ' ' : '') + x.toFixed(2);
  }
  $('convDot').className = 'dot ' + (m.conveyor ? 'bg-emerald-400' : 'bg-slate-600');
  $('convChip').lastChild.textContent = m.conveyor ? 'Conveyor on' : 'Conveyor off';
  $('convChip').classList.toggle('text-emerald-300', !!m.conveyor);

  $('trail').textContent = m.trail_len ?? '--';
  const f = $('fence');
  f.textContent = fencePct == null ? '--' : `${Math.round(fencePct)} %`;
  f.className = 'mid mt-1 ' + (fencePct >= 80 ? 'text-amber-200' : 'text-bone');
  setGps(m.gps_fix, m.sats ?? 0);
}

export function setLastSeenText(text) { $('lastSeen').textContent = text; $('lastSeen').className = 'num text-[12px] text-mist/60'; }

export function setLastSeen(secondsAgo, hz) {
  const el = $('lastSeen');
  if (secondsAgo == null) { el.textContent = 'no data'; return; }
  el.textContent = secondsAgo < 2.5 ? (hz ? `live · ${hz < 1.5 ? hz.toFixed(1) : Math.round(hz)} Hz` : 'live') : `${Math.round(secondsAgo)} s ago`;
  el.className = 'num text-[12px] ' + (secondsAgo < 2.5 ? 'text-mist/50' : 'text-amber-200');
}

export function setCoverage(pct) { $('cov').textContent = pct == null ? '--' : `${Math.round(pct)} %`; }

export function setTrash(collected, total, live) {
  const row = $('trashRow');
  row.classList.toggle('hidden', !live);
  row.classList.toggle('flex', live);
  $('trashCount').textContent = `${collected} / ${total}`;
  if (live && collected !== setTrash.last && setTrash.last != null && !reduce) animate($('trashCount'), { scale: [1.3, 1] }, { type: 'spring', stiffness: 500, damping: 20 });
  setTrash.last = collected;
}

export function setSweep(i, n) {
  $('sweepCount').textContent = n ? `${Math.min(i ?? 0, n)} / ${n} waypoints` : 'no sweep';
  $('sweepBar').style.width = n ? `${(100 * Math.min(i ?? 0, n)) / n}%` : '0%';
}

export function setLegend(layer, range, unit, rampCss) {
  const box = $('legend');
  if (layer === 'covered') { box.classList.add('hidden'); return; }
  box.classList.remove('hidden');
  $('legendRamp').style.background = `linear-gradient(90deg, ${rampCss.join(', ')})`;
  $('legendLo').textContent = `${range[0]}${unit}`;
  $('legendHi').textContent = `${range[1]}${unit}`;
  if (!reduce) animate(box, { opacity: [0, 1] }, { duration: 0.25 });
}

// ---------------------------------------------------------------------------------------------
// event log
// ---------------------------------------------------------------------------------------------
const EVENTS = {
  link_lost: ['Link lost', 'crit'], link_back: ['Link restored', 'ok'],
  station_link_down: ['Station lost the boat', 'crit'], station_link_up: ['Station hears the boat', 'ok'],
  batt_warn: ['Battery low', 'warn'], batt_low: ['Battery: coming home', 'crit'], batt_critical: ['Battery critical: motors off', 'crit'],
  fence_exit: ['Left the fence', 'warn'], fence_back_inside: ['Back inside the fence', 'ok'],
  mode_change: ['Mode changed', 'info'], wp_reached: ['Waypoint reached', 'info'], sweep_done: ['Sweep complete', 'ok'],
  backing_up: ['Backing up to good signal', 'warn'], going_home: ['Following the trail home', 'warn'], home_done: ['Home reached', 'ok'],
  trash_marked: ['Trash marked', 'info'], trash_seen: ['Trash seen', 'info'],
  arduino_stop_no_pi: ['Arduino watchdog stopped the motors', 'crit'], arduino_gps_lost: ['GPS fix lost', 'warn'], arduino_batt_low: ['Arduino: battery threshold', 'warn'],
  ack_ok: ['Boat accepted', 'ok'], ack_refused: ['Boat refused', 'warn'],
};
export const eventTitle = (kind) => (EVENTS[kind] ?? [kind.replace(/_/g, ' ')])[0];
const SEV = { ok: 'bg-emerald-400', info: 'bg-sky-400', warn: 'bg-amber-400', crit: 'bg-red-400' };

function prettyDetail(kind, d) {
  if (!d) return '';
  if (kind === 'mode_change') {
    return d.replace(/\b(DRIVEN|AUTO|COMING_HOME)\b/g, (m) => modeWord(m)).replace(' -> ', ' → ').replace(/\(([a-z_]+)\)/, (_, r) => `· ${r.replace(/_/g, ' ')}`);
  }
  return d.replace(/_/g, ' ');
}

const seen = new Set();
let total = 0;
export function addEvent({ kind, detail = '', ts }, { animateIn = true } = {}) {
  ts = ts ?? Date.now() / 1000;
  // the same event can arrive twice (history on reconnect, the boat re-sending held events)
  const key = `${kind}|${detail}|${ts.toFixed(2)}`;
  if (seen.has(key)) return;
  seen.add(key);

  const list = $('events');
  const top = list.firstElementChild;
  const [title, sev] = EVENTS[kind] ?? [kind.replace(/_/g, ' '), 'info'];
  const text = prettyDetail(kind, detail);
  // a button pressed five times is one line with "×5", not five lines
  if (top && top.dataset.kind === kind && top.dataset.detail === text && ts - Number(top.dataset.ts) < 20) {
    const n = Number(top.dataset.n) + 1;
    top.dataset.n = n;
    top.dataset.ts = ts;
    const badge = top.querySelector('[data-count]');
    badge.textContent = `×${n}`;
    badge.classList.remove('hidden');
    top.querySelector('time').textContent = clock(ts);
    if (!reduce) animate(badge, { scale: [1.35, 1] }, { type: 'spring', stiffness: 600, damping: 18 });
    return;
  }
  const li = document.createElement('li');
  li.dataset.kind = kind; li.dataset.detail = text; li.dataset.ts = ts; li.dataset.n = 1;
  li.className = 'flex items-start gap-3 border-b border-bone/[0.06] py-2.5';
  li.innerHTML = `
    <span class="mt-[7px] size-1.5 shrink-0 rounded-full ${SEV[sev]}"></span>
    <div class="min-w-0 flex-1">
      <div class="flex items-center gap-1.5 text-[13px] text-bone">${title}<span data-count class="num hidden rounded-full border border-bone/15 px-1.5 text-[10px] text-mist/80"></span></div>
      ${text ? `<div class="truncate text-[12px] text-mist/55" title="${text.replace(/"/g, '&quot;')}">${text}</div>` : ''}
    </div>
    <time class="num shrink-0 pt-px text-[11px] text-mist/45">${clock(ts)}</time>`;
  list.prepend(li);
  while (list.children.length > 150) list.lastElementChild.remove();
  $('evtCount').textContent = ++total;
  if (animateIn && !reduce) animate(li, { opacity: [0, 1], x: [10, 0] }, { duration: 0.35, ease: EASE });
  return sev;
}
const clock = (ts) => new Date(ts * 1000).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit', second: '2-digit', hour12: false });

// ---------------------------------------------------------------------------------------------
// toasts
// ---------------------------------------------------------------------------------------------
const TONE = {
  ok: ['border-emerald-400/25', 'text-emerald-300'],
  info: ['border-sky-400/25', 'text-sky-300'],
  warn: ['border-amber-400/30', 'text-amber-300'],
  crit: ['border-red-400/35', 'text-red-300'],
};
export function toast(tone, title, body = '', ms = 4500) {
  const el = document.createElement('div');
  el.setAttribute('role', 'status');
  el.className = `pointer-events-auto rounded-2xl bg-ink/85 px-4 py-3 shadow-[0_20px_50px_-20px_rgb(0_0_0/0.9)] backdrop-blur-md`;
  el.innerHTML = `<div class="text-[13px] ${TONE[tone][1]}">${title}</div>${body ? `<div class="mt-0.5 text-[12.5px] leading-snug text-mist/70">${body}</div>` : ''}`;
  const box = $('toasts');
  box.append(el);
  while (box.children.length > 3) box.firstElementChild.remove();
  if (!reduce) animate(el, { opacity: [0, 1], y: [14, 0], scale: [0.98, 1] }, { type: 'spring', stiffness: 420, damping: 32 });
  setTimeout(async () => {
    if (!reduce) await animate(el, { opacity: 0, y: 6 }, { duration: 0.2 });
    el.remove();
  }, ms);
}

export function shake(el) {
  if (!reduce) animate(el, { x: [0, -5, 5, -3, 3, 0] }, { duration: 0.38 });
}

// ---------------------------------------------------------------------------------------------
// banner, vignette, overlays
// ---------------------------------------------------------------------------------------------
export function show(el, on, how = 'drop') {
  if (on === !el.classList.contains('hidden')) return;
  if (on) {
    el.classList.remove('hidden'); el.classList.add('flex');
    if (!reduce) animate(el, { opacity: [0, 1], y: how === 'drop' ? [-10, 0] : [10, 0] }, { duration: 0.35, ease: EASE });
  } else if (reduce) {
    el.classList.add('hidden'); el.classList.remove('flex');
  } else {
    animate(el, { opacity: 0, y: how === 'drop' ? -8 : 8 }, { duration: 0.2 }).then(() => { el.classList.add('hidden'); el.classList.remove('flex'); });
  }
}
export function setVignette(on) {
  animate($('vignette'), { opacity: on ? 1 : 0 }, { duration: reduce ? 0 : 0.6 });
}
