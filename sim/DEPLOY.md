# Put the sim on a public link

So anyone can open a URL and drive the boat. Uses Fly.io because it runs long-lived processes and WebSockets, which the station needs. Free tier is enough.

This is a demo link only. The real ground station runs on a Pi on the shore and serves the same page over its own Wi-Fi.

## One-time setup (about 5 minutes)

1. Install the Fly command line: https://fly.io/docs/flyctl/install/
   - Mac: `brew install flyctl`
   - Windows: `pwsh -Command "iwr https://fly.io/install.ps1 -useb | iex"`
   - Linux: `curl -L https://fly.io/install.sh | sh`
2. `fly auth signup` (or `fly auth login` if you have an account). It will ask for a card; the free allowance covers this.
3. From the repo root, on the `sim` branch:
   ```bash
   fly launch --copy-config --name ewbboat --region iad --no-deploy
   ```
   If the name is taken, pick another; it becomes the URL. Say **no** to adding a Postgres or Redis.
4. Deploy:
   ```bash
   fly deploy
   ```
   First build takes a couple of minutes. When it finishes:
   ```
   https://ewbboat.fly.dev/viewer
   ```

## Every time after that

```bash
git checkout sim && git pull
fly deploy
```

## Good to know

- **One boat, many viewers.** Everyone who opens the link sees the same boat. Only one person holds control at a time (Take control). Others watch.
- **It sleeps.** With nobody connected the machine stops; the first visitor waits ~5 s while it wakes and the boat starts from the launch spot again.
- **Reset it.** `fly machine restart` puts the boat back at the start.
- **Change the scenario.** Edit the `CMD` line in `Dockerfile` (e.g. add `--range 120` or `--drain 20`) and `fly deploy`.
- **Logs.** `fly logs` shows the boat's event stream live.
- **Cost.** A shared-cpu-1x that sleeps when idle sits inside Fly's free allowance. Check `fly dashboard` if unsure.
