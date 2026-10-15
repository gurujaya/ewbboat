# sim

The whole boat on one laptop, no hardware. The real `boat-pi` and `ground-station` code runs unchanged; only the Arduino and the water are fake.

```
                  pty (/tmp/boat-serial)            UDP 127.0.0.1               WebSocket
 fake_arduino.py  <--------------------->  boat-pi/main.py  <---------->  ground-station/main.py  <--------->  browser
 (physics.py)         M / T / S lines         (the real code)    cmd/hb/tlm      (the real code)           /viewer (three.js)
```

## Run it

```bash
pip install -r boat-pi/requirements.txt -r ground-station/requirements.txt
python sim/run.py
# open http://localhost:8000/viewer
```

In the viewer: **Take control**, then drive with W A S D (or a gamepad). **Start sweep**, then click two corners on the water. **Come home**. Watch the trail dots change color as the signal weakens, and drive past the radio range to see the boat stop, wait, back up, and come home on its own.

Knobs:

```bash
python sim/run.py --range 120          # radio dies at 120 m (default 200)
python sim/run.py --current 0.4,0.1    # strong current pushing east
python sim/run.py --noise 3            # worse GPS
python sim/run.py --drain 20           # battery dies in minutes; watch 30/20/10 % fire
python sim/run.py --start 0,80         # launch 80 m out
```

## Prove it works without a browser

```bash
pip install websockets
python sim/headless_test.py
```

Drives north, sweeps a 30 × 20 m rectangle, drives out of radio range, and checks the boat comes back. Takes about 8 minutes. Run it before opening a pull request that touches `boat-pi`, `ground-station`, or `comms`.

## What's fake and what's real

| Piece | In the sim | On the boat |
| --- | --- | --- |
| Arduino | `fake_arduino.py` on a pty, same `M`/`T`/`E` lines plus a sim-only `S <dbm>` line | the real board on `/dev/ttyUSB0` |
| Water, current, GPS noise, battery drain | `physics.py` | the lake |
| Radio | `boatlink` over localhost; packets dropped when the fake signal is below −88 dBm | `boatlink` over the Wi-Fi bridges |
| Signal strength | from the `S` line | `iw dev wlan0 link` |
| Everything else | real code | real code |

Switching to hardware is `BOAT_ENV=boat` plus the addresses in `boat-pi/config.py` and `ground-station/config.py`.

## Files

```
sim/
  physics.py        the boat: thrust, turning, lag, current, slowly-drifting GPS error, battery drain
  fake_arduino.py   speaks the serial protocol over a pty; 2 s watchdog like the real firmware
  run.py            starts all three processes with the right environment
  headless_test.py  end-to-end check, no browser
  viewer/index.html three.js view of the lake. Reads the station's /ws, so it also shows the real boat.
```

## Things the sim found already

- A sweep rectangle used as the fence before the boat had reached it kicked the boat out of AUTO on the first tick. Now the fence only applies after the first waypoint.
- A boat can orbit a waypoint it keeps missing by a meter. "Arrived" now also counts when the point is close and behind the boat.
- The boat's `link_lost` event is sent over the link that just died, so it never arrived. Events are now held and delivered when the link returns.
- At the edge of range the link flickered on and off every second. The boat now needs 4 dB of margin before it calls the link good again.

None of those would have been fun to discover on the lake.
