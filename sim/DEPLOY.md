# Put the sim on a public link

So anyone on the team (or a judge) can open a URL and watch or drive the boat. This is a demo
link only: the real ground station runs on a Pi on the shore and serves the same page over its
own Wi-Fi.

## The free way: the simulator inside the browser (GitHub Pages, Vercel, any static host)

The page can run the whole simulator itself, with no server: the real `Boat` class from
`boat-pi/main.py` and the real `Station` class from `ground-station/main.py` run inside the page
under Pyodide (Python compiled to WebAssembly), with in-memory stand-ins for the radio and the
Arduino (`sim/browser/core.py`). Each visitor gets their own boat; nothing sleeps; it costs nothing.
What doesn't run there: the C++ firmware and the UDP radio code. The real simulator (`sim/run.py`)
runs both, and that's what the headless test checks.

- **GitHub Pages** (already set up): every push to `demo` or `main` runs `.github/workflows/pages.yml`,
  which builds the static site (`python sim/browser/build_site.py site`) and publishes it at
  **https://gurujaya.github.io/ewbboat/** . No account beyond GitHub, no card, no sleeping.
- **Vercel / Netlify / Cloudflare Pages**: run `python sim/browser/build_site.py site` and deploy the
  `site` folder as a static site (Vercel: `vercel site --prod`). Same result.
- The page decides by itself: if a ground station answers at `../api/grid` it uses the WebSocket;
  otherwise it starts the in-browser simulator. `?local=1` forces the in-browser one.

## What the host has to run (the full simulator, with the firmware and the radio code)

The sim is **four long-running processes in one container** (the fake Arduino, the firmware
compiled for the machine, the real boat-pi, the real ground station), talking to each other over
local sockets, with a **WebSocket** to every browser. That rules out the static/serverless hosts:

| Host | Can it run this? | Why |
| --- | --- | --- |
| Vercel, Netlify, GitHub Pages, Cloudflare Pages | Not the full sim | Static files only: no long-running process, no WebSocket server. They host the in-browser version above, which is what the public link uses. |
| Fly.io | Yes | Already set up here (`fly.toml`, app `ewbboat`). Not free for new accounts since 2024; a machine that sleeps when idle costs about $0–2 a month. |
| Hugging Face Spaces (Docker) | Yes, **$9/month** | Docker Spaces need a PRO subscription now (checked 2026-10-17: the free tier only hosts static pages). 2 vCPU, WebSockets, sleeps after 48 h idle. |
| Render (free web service) | **Yes, free** | Docker, WebSockets, 512 MB. Sleeps after 15 min idle; the first visitor waits ~30–60 s. No card. |
| Koyeb (free instance) | Yes, free | Docker, WebSockets, one small instance, scales to zero. |
| Google Cloud Run | Yes, free tier | WebSockets, scales to zero; needs a card on the account. |
| Oracle Cloud "always free" VM | Yes, free | A real server; you install Docker and a reverse proxy yourself. Most work. |

**Recommendation.** Render for a free link (no card; small CPU, sleeps when idle). Fly if ~$1–2/month
is fine (fastest to update, one command). Hugging Face only if someone already has PRO.

The container reads the web port from `$PORT` (every host above sets it), serves the viewer at
`/viewer`, and passes the simulator's trash "ground truth" feed through on the same origin
(`/api/sim/truth`), so the floating litter and the scooped count show on a public link too.

---

## Option A: Fly.io (already configured)

One-time: `brew install flyctl`, then `fly auth login`. The app `ewbboat` already exists.

```bash
fly scale count 1 -a ewbboat      # one machine = one boat (two machines would be two different boats)
fly deploy --remote-only          # builds the Dockerfile on Fly's builder; ~3 min the first time
```

Then open **https://ewbboat.fly.dev/viewer**.

**If `fly deploy` fails with `x509: certificate signed by unknown authority`** (it does from some
Macs: something on the machine intercepts the TLS to Fly's remote builder), build the image
locally and deploy from it instead. Docker Desktop must be running; its credential helper lives
inside Docker.app, so put it on the PATH first:

```bash
export PATH="/Applications/Docker.app/Contents/Resources/bin:$PATH"
TAG=registry.fly.io/ewbboat:v$(date +%Y%m%d%H%M)
docker build --platform linux/amd64 -t $TAG .      # Fly machines are amd64; ~5 min on an Apple-silicon Mac
fly auth docker && docker push $TAG
fly deploy -a ewbboat --image $TAG
```

- With nobody connected the machine stops; the first visitor waits ~5 s while it wakes, and the
  boat starts at the jetty again.
- `fly logs -a ewbboat` shows the boat's events live. `fly machine restart` resets the boat.
- `.github/workflows/fly-deploy.yml` redeploys on every push to `main` if the repo has a
  `FLY_API_TOKEN` secret (`fly tokens create deploy` → GitHub → Settings → Secrets).

## Option B: Hugging Face Spaces (needs PRO, $9/month)

Docker Spaces are not on the free tier any more (`402 Payment Required` on create, 2026-10-17). With PRO: 2 vCPU, Docker, WebSockets. Sleeps after 48 h with no
visitors and wakes on the next one. The Space builds the repo's `Dockerfile`; the YAML block at
the top of the repo's `README.md` (`sdk: docker`, `app_port: 8080`) is what tells it how.

1. Free account at https://huggingface.co. Then on your laptop:
   ```bash
   pip install -U huggingface_hub
   hf auth login --add-to-git-credential      # opens the browser; the token stays on your machine
   ```
2. Create the Space and push the `demo` branch to it (Spaces build from their `main`):
   ```bash
   hf repos create ewbboat --repo-type space --space_sdk docker
   git push https://huggingface.co/spaces/<your-hf-name>/ewbboat demo:main
   ```
3. Open `https://huggingface.co/spaces/<your-hf-name>/ewbboat`. The first build takes ~5 minutes.
   The viewer is at `https://<your-hf-name>-ewbboat.hf.space/viewer` (the Space page embeds it).
4. To update: push the branch again. To reset the boat: Settings → Factory reboot.

## Option C: Render (free)

1. Free account at https://render.com → **New → Web Service** → connect the GitHub repo.
2. Runtime **Docker**, instance type **Free**. Render sets `$PORT` itself; nothing to configure.
3. Deploy. The URL is `https://<service>.onrender.com/viewer`.
4. Free services sleep after 15 minutes idle; the first visitor waits ~30–60 s. Redeploys on every push.

## Good to know, any host

- **One boat, many viewers.** Everyone who opens the link sees the same boat. One person holds
  control at a time (Drive); the rest watch. If two machines/instances run, they are two boats.
- **Scenario.** Add flags to the `CMD` line in `Dockerfile`, e.g. `"--range", "120"` or
  `"--drain", "20"`, and redeploy. Row spacing: an env var `ROW_SPACING_M=3` for quick demos.
- **Memory.** About 150 MB; 256–512 MB instances are fine.
- **Not for the lake.** The station on the shore runs from `ground-station/`, not from a cloud.
