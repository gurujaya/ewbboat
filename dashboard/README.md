# dashboard

The web page the driver and everyone else looks at. Served by the ground station; opens on any laptop or phone. Plain HTML, CSS, and JavaScript, no build step, so anyone can open the file and edit it.

Owner: **Sebastian Norberte** (`SebastianNorberte`). Branch: `dashboard`.

## What it shows

- Live video, big
- Map: boat marker and heading, trail (colored by signal), the fence / sweep rectangle, coverage overlay, heat map layer, trash pins
- The four water readings, battery %, signal, mode
- Event feed (link lost, battery warning, waypoint reached…)
- Buttons: Take control, Start sweep, Come home, Export CSV, Mark trash
- "LINK LOST" state when the station loses the boat

## How it gets data

One WebSocket to the station (`/ws`) that pushes every message the boat sends. It sends the operator's input back as small JSON objects; the station turns those into `cmd` messages. See [`../docs/MESSAGES.md`](../docs/MESSAGES.md).

The browser reads the gamepad itself with the Gamepad API (`navigator.getGamepads()`), polled at 10 Hz while this page holds control.

## Layout (to create)

```
dashboard/
  index.html
  style.css
  js/
    ws.js          connect, reconnect, dispatch messages to the panels
    video.js       play the stream
    map.js         Leaflet map, boat marker, trail, fence, grid overlay, pins
    readings.js    the strip at the bottom
    gamepad.js     poll the gamepad, send throttle/steer/conveyor at 10 Hz
    control.js     take-control button and lock state
    sweep.js       draw a rectangle, send it, show progress
    feed.js        event list
  vendor/          leaflet.js and css, vendored so it works offline
```

## Run it without the boat

Start the station with `--fake-boat` (see `../ground-station/README.md`) and open `http://localhost:8000`. The whole page should work against replayed data.

## Rules

- No framework unless the team agrees. Vanilla JS is fine for this.
- Offline first: no CDN links. Map tiles will be a local tile cache of the test site; until then, a plain grid background is fine.
- The page never decides a mode. It asks, then shows what the boat answered.
- Keep it readable on a phone in sunlight: big numbers, high contrast.
