// The simulator inside the browser (a Web Worker), for static hosts with no server to run.
//
// Loads Pyodide (CPython compiled to WebAssembly), copies the repo's Python files into its
// file system, and runs sim/browser/core.py: the real boat-pi Boat and ground-station Station
// classes with in-memory fakes for the radio and the Arduino. The page talks to it with the
// same JSON messages it would send a real station over the WebSocket.
//
// Messages in:  { type: 'init', pyBase }        where to fetch the .py files from
//               { type: 'send', data }          a message from the page (JSON string)
//               { type: 'truth' }               ask for the sim-only ground truth
//               { type: 'csv' }                 ask for the telemetry export
// Messages out: { type: 'ready' } | { type: 'status', text } | { type: 'msgs', list }
//               { type: 'truth', data } | { type: 'csv', data } | { type: 'error', text }

const PYODIDE = 'https://cdn.jsdelivr.net/pyodide/v0.27.7/full/';
importScripts(PYODIDE + 'pyodide.js');

// the Python the demo needs, at their repo paths (sim/browser/build_site.py copies these under py/)
const FILES = [
  'boat-pi/config.py', 'boat-pi/main.py', 'boat-pi/modes.py', 'boat-pi/nav.py', 'boat-pi/autopilot.py',
  'boat-pi/safety.py', 'boat-pi/trail.py',
  'comms/boatlink/__init__.py', 'comms/boatlink/messages.py', 'comms/boatlink/link.py',
  'ground-station/config.py', 'ground-station/main.py', 'ground-station/db.py', 'ground-station/grid.py', 'ground-station/sweep.py',
  'sim/physics.py', 'sim/browser/core.py',
];

const CID = 'page';
let sim = null;

const status = (text) => postMessage({ type: 'status', text });

async function init(pyBase) {
  status('Loading Python…');
  const pyodide = await loadPyodide({ indexURL: PYODIDE });
  await pyodide.loadPackage('sqlite3');       // the station's db.py imports it; Pyodide ships it separately
  status('Loading the boat…');
  const srcs = await Promise.all(FILES.map(async (f) => {
    const r = await fetch(new URL(f, pyBase), { cache: 'no-cache' });
    if (!r.ok) throw new Error(`missing ${f} (${r.status})`);
    return [f, await r.text()];
  }));
  for (const [f, text] of srcs) {
    const path = '/repo/' + f;
    pyodide.FS.mkdirTree(path.slice(0, path.lastIndexOf('/')));
    pyodide.FS.writeFile(path, text);
  }
  await pyodide.runPythonAsync(`
import sys, asyncio
sys.path.insert(0, '/repo/sim/browser')
import core
sim = core.BrowserSim()
sim.start()
sim.connect('${CID}')
`);
  sim = pyodide.globals.get('sim');
  postMessage({ type: 'ready' });

  // the lake runs at 20 Hz; what the station would send goes to the page in batches
  setInterval(() => {
    try { sim.step(); } catch (e) { postMessage({ type: 'error', text: String(e).slice(0, 4000) }); }
  }, 50);
  setInterval(() => {
    const out = sim.drain(CID);
    const list = out.toJs();
    out.destroy();
    if (list.length) postMessage({ type: 'msgs', list });
  }, 100);
}

onmessage = async (e) => {
  const m = e.data;
  try {
    if (m.type === 'init') await init(m.pyBase);
    else if (!sim) { if (m.type === 'truth' || m.type === 'csv') postMessage({ type: 'busy' }); return; }
    else if (m.type === 'send') sim.handle_json(CID, m.data);
    else if (m.type === 'truth') postMessage({ type: 'truth', data: sim.truth_json() });
    else if (m.type === 'csv') postMessage({ type: 'csv', data: sim.export_csv() });
  } catch (err) {
    postMessage({ type: 'error', text: String(err).slice(0, 4000) });
  }
};
