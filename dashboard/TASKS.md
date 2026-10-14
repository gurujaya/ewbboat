# dashboard tasks

## Phase 1
- [ ] Agree the page layout (sketch in the deck: video left, map right, readings strip, buttons)
- [ ] Vendor Leaflet into `vendor/`

## Phase 2: table
- [ ] `ws.js`: connect to the station, auto-reconnect, dispatch by `t`
- [ ] `video.js`: play the station's stream
- [ ] `readings.js`: four water readings, battery, signal, mode, with units
- [ ] `map.js`: boat marker with heading arrow
- [ ] `gamepad.js`: read a gamepad, send throttle/steer/conveyor at 10 Hz while holding control
- [ ] `control.js`: Take control button, lock shown to other viewers
- [ ] Keyboard fallback (WASD) for when nobody brought a gamepad
- [ ] Test: works on a phone and a laptop at the same time

## Phase 3: coming home
- [ ] Trail drawn live, colored by signal strength
- [ ] Fence drawn; warning at 80 % of the way to the edge
- [ ] Come home button
- [ ] Event feed panel
- [ ] "LINK LOST" state: grey boat, banner, buttons disabled
- [ ] Export CSV button
- [ ] Battery warning at 30 %

## Phase 4: autopilot and map
- [ ] `sweep.js`: draw a rectangle on the map, send it, show the waypoint list and which one is next
- [ ] Coverage overlay from `/api/grid`
- [ ] Heat map layer with a selector (pH / turbidity / temp / conductivity)
- [ ] Mark trash button (drops a pin at the boat's position)
- [ ] Coverage % and "sweep what's missed"
- [ ] Showcase mode: a clean full-screen map + video view for the big screen

## Always
- [ ] Any new message field used here is already in `docs/MESSAGES.md`
