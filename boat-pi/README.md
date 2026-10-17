# boat-pi

The Python on the boat's Raspberry Pi. This is the brain: radio link to shore, camera, trail points, the coming-home rules, and the autopilot.

Owner: **Zachary Kamba** (`zachkam1`), pairing with Guru on the Arduino serial link. Branch: `boat-pi`. Language: Python 3.11+.

## What it owns

- UDP link to the ground station: heartbeat, `cmd` in, `tlm`/`trail`/`evt`/`ack` out
- Serial link to the Arduino: `M` out at 10 Hz, `T` and `E` in
- Camera stream
- Trail points (every 3 m or 5 s, with signal strength)
- Modes: `DRIVEN`, `AUTO`, `COMING_HOME`, and every safety transition
- Lost-signal procedure, low-battery rules, fence check
- Algorithm 1 (go to waypoint) and running a waypoint list
- Logging every `tlm` to CSV on the SD card

Everything it sends or receives is in [`../docs/MESSAGES.md`](../docs/MESSAGES.md). The rules are in [`../docs/ARCHITECTURE.md`](../docs/ARCHITECTURE.md), Levels 2 and 3.

## Layout (to create)

```
boat-pi/
  main.py             starts everything, the 10 Hz main loop
  config.py           ports, addresses, thresholds (3 s, 10 s, 2 m, Kp, -75 dBm...)
  radio.py            thin wrapper around comms/boatlink (Eric's package); no socket code here
  arduino.py          serial: send M lines, parse T and E lines
  telemetry.py        build tlm from the latest Arduino data + radio + mode
  trail.py            save points, find last good-signal point, walk backwards
  modes.py            the state machine; the only place mode changes happen
  nav.py              bearing, distance, wrap, GPS filter, pure-pursuit math, trail simplify, fences
  autopilot.py        PathFollower: follow a list of points with pure pursuit (algorithm 1)
  safety.py           lost-signal, battery, fence checks → asks modes.py to switch
  camera.py           start/stop the video stream
  logger.py           CSV on the SD card
  tests/              unit tests for nav.py, trail.py, modes.py, safety.py
  requirements.txt
```

## Setup

```bash
sudo apt install python3-venv python3-picamera2
cd boat-pi
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp config.example.py config.local.py   # fill in addresses; config.local.py is gitignored
python main.py
```

## Rules

- Motor commands go to the Arduino **only** through `arduino.send_motors(left, right, conveyor)`. The gamepad path and the autopilot path both end there.
- Mode changes happen **only** in `modes.py`. Safety code asks; `modes.py` decides.
- No `cmd` from shore for 3 s is not the same as no heartbeat for 3 s. Heartbeat drives lost-signal. Missing `cmd` just means nobody is driving; hold position.
- The Pi sends `M 0 0 0` when it has nothing better to say. Never stop sending `M` lines while running, or the Arduino watchdog fires.
