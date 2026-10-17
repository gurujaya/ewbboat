# Architecture

How the boat is controlled, how data gets to shore, and what the boat does on its own. Written for the whole team, not just software people. Goes from basic to advanced; each level works on its own.

## The three parts

```
 laptop / phone  <--- station's Wi-Fi --->  ground station  <--- long-range Wi-Fi --->  the boat
```

**The boat.** Two small computers.
- *Arduino (C++)* does: runs the two thrusters and the conveyor, reads the four water sensors, GPS, compass, and battery voltage, and stops the motors if the Pi goes quiet.
- *Raspberry Pi (Python)* thinks: talks to shore over the radio, streams the camera, drops trail points, runs the coming-home rules and the autopilot, saves everything to its SD card.
- They talk over a USB serial cable.

Why two: if the Pi crashes, the Arduino notices the silence and cuts the motors. One bug in our Python can never strand the boat.

**The ground station.** A Raspberry Pi in a waterproof box on shore, antenna on a pole, always on. It keeps the link to the boat, saves every reading in a SQLite database, builds the map, and hosts the dashboard as a web page. It makes its own Wi-Fi network for laptops and phones to join.

Why a station and not just a laptop: the trail, the data, and the map need a home that doesn't close its lid. A laptop sleeping or walking away must never cost us the link or a reading.

**The laptop (or phone).** Joins the station's Wi-Fi, opens the dashboard in a browser. Nothing to install. Drives with a gamepad after pressing "Take control." Only one driver at a time; everyone else watches.

## The two links

- **Boat ↔ station:** a pair of outdoor Wi-Fi bridge radios. Height of the antenna matters more than anything for range over water. Later, a cheap LoRa radio can be a slow backup for commands if the Wi-Fi drops.
- **Station ↔ laptop:** the station's own short-range Wi-Fi.

## Four message types

Only four things ever cross the water. Field-by-field definitions are in [MESSAGES.md](MESSAGES.md).

| Message | Direction | What's in it | How often |
| --- | --- | --- | --- |
| Command | laptop → station → boat | steering, speed, conveyor on/off, mode | ~10/s while driving |
| Heartbeat | both ways | "I'm still here" | several/s, always |
| Telemetry | boat → station | position, heading, speed, battery, signal, 4 water readings | 5/s |
| Video | boat → station | camera feed | continuous, own stream |

Commands, heartbeat, and telemetry go over UDP. Video is a separate stream so a frozen video never blocks a command.

---

## Level 1: remote control

A person drives from the dashboard. Video and readings come back. This alone meets every project requirement.

**Steering.** Two thrusters, no rudder. The gamepad gives `throttle` and `steer`, each in [-1, +1]:

```
left  = throttle + steer
right = throttle - steer
clamp both to [-1, +1]
```

Both equal → straight. Left faster → turns right. One forward, one reverse → spins in place. Reverse is negative throttle. The Arduino only ever sees `left` and `right`; it doesn't know a gamepad exists.

**Dashboard.** Big live video, a map (boat, its trail, the allowed area, trash pins, covered squares), the four water readings, battery, signal, mode. Buttons: Take control, Start sweep, Come home. Export the run as a spreadsheet.

**Logging.** Every telemetry message is saved on the station (SQLite) and on the boat (SD card, CSV). Each row has a timestamp and a GPS position.

---

## Level 2: comes home on its own

When the signal is gone nobody can tell the boat anything, so the plan has to already be on board. Same two ideas a Roomba uses: remember where you've been, and know where home is.

**Home.** The boat always starts the run at the jetty next to the station, and that's where it comes back to. The Pi takes the first 3 s of GPS fixes after power-on (while the boat sits still) and averages them into trail point 0. One noisy fix would otherwise become the spot the boat aims for at the end of every trip home.

**Trail points.** Every ~3 m or every 5 s (whichever comes first) the Pi saves a point:

```
{ lat, lon, time, signal_dbm }
```

The list of points is the trail. It is also sent to the station so the dashboard can draw it.

Before following the trail, the boat makes a cleaned-up copy: points bunched closer than 1.5 m are dropped, and stretches that are straight to within 1 m become one straight line (Douglas-Peucker). The corners stay; the GPS wobble goes. The trail itself is kept exactly as recorded.

**Two different ways home.** When the operator presses *Come home* (or the battery is low), the boat takes the fastest way: a straight line to the launch point. When the *link is lost*, nobody can see the boat, so it retraces its own trail: water it has just been through and knows is clear, back to where it last had signal. The straight line assumes open water between the boat and home; that holds inside the driving fence (a circle of open water round the station, sized by the test site) and is why the fence matters.

**Lost signal.**
1. No heartbeat from the station for 3 s → stop the motors, keep logging, wait 10 s.
2. Signal back? Carry on as before.
3. No? Drive back along the trail to the last point whose signal was good (above a threshold, e.g. -75 dBm).
4. Signal back? Carry on.
5. No? Keep following the trail all the way to the launch point. Stop there and wait.

Why "last good signal" and not "last point": if the boat lost the signal at a spot, sitting there won't help. It has to move toward the station until the link returns.

**Second safety layer.** If the Arduino hears nothing from the Pi for 2 s, it cuts the motors. No GPS, no Python, can't be crashed by our bugs.

**Low battery.** The Arduino reads battery voltage and sends it with telemetry. Percentages below are placeholders until Electrical gives real pack voltages. The reading is averaged over a few seconds so a motor surge doesn't trigger a false alarm.

| Battery | What happens |
| --- | --- |
| above 30 % | normal |
| 30 % | warning on the dashboard |
| 20 % | conveyor off, sensors keep going, follow the trail home |
| 10 % | motors off, logging continues, so the pack isn't damaged |

The 20 % threshold is sized to the trip home, not to empty. Range testing sets the real number.

**Testing rule.** A stopped boat drifts. Every water test has a rope on the boat or a kayak nearby.

---

## Level 3: drives itself

Same four-step loop every self-driving thing runs, 10 times a second: perceive → localize → plan → control. Tesla does it with 8 cameras and a custom chip. We do it with a GPS and a compass, because our job is to reach the next dot inside a rectangle.

**Localize: smooth the GPS.** The Arduino sends GPS and compass 5 times a second. A raw GPS fix jumps around by a meter or so from one reading to the next, so the Pi runs every fix through a small filter (an alpha-beta filter, `boat-pi/nav.py`): it keeps a position and a velocity, predicts where the boat should be at the next fix, and moves only part of the way toward what the GPS says. Between fixes it predicts. Everything on the boat uses this filtered position: the autopilot, the fences, the trail, and the `lat`/`lon` in telemetry. Speed over ground comes from the filter's velocity. If the fix drops, or jumps somewhere absurd several times in a row, the filter starts over.

The filter can't remove GPS error that drifts slowly (a meter or two over tens of seconds); nothing short of a better GPS can. It removes the fast jitter that made the autopilot zig-zag.

**Algorithm 1: follow a path (pure pursuit).** The whole autopilot. A path is a list of points: the sweep rows, or the trail home.

```
every 100 ms:
  pos, heading = filtered position, compass
  progress     = where pos is along the path (meters), never going backwards
  target       = the point 3 m further along the path    # LOOKAHEAD_M
  bearing      = direction from pos to target            # 0..360, clockwise from north
  error        = wrap(bearing - heading)                 # -180..180
  steer        = Kp * error + Kd * (how fast error is changing)
  speed        = 0.6, less only near the LAST point or when pointing far off
  send(left = speed + steer, right = speed - steer)
  done when within 2 m of the last point, or past it
```

Like driving a car down a road: look a little way ahead and steer toward that spot. The boat never has to "arrive" at each point, so it doesn't slow down at every one of them, and when the current pushes it sideways the target is still on the line, so it steers back. `LOOKAHEAD_M` is the main knob: shorter hugs the line but wiggles, longer is smooth but cuts corners. `Kp` and `Kd` are tuned in the sim (`config.py`); re-tune them in the pool.

Why not "go to the next point, then the next": that's what we did first. It slowed to a crawl near every point (the trail has one every 3 m), had to hit each one within 2 m, and faithfully re-drove every GPS wobble recorded in the trail.

**Algorithm 2: sweep (lawnmower / boustrophedon).**
1. Operator draws a rectangle on the dashboard map. Its corners are also the fence.
2. The station turns it into a numbered list of waypoints, row by row, alternating direction. Row spacing = 0.8 × the scoop width, so GPS error and current don't leave gaps between rows. The scoop is the gap between the pontoons (Rev C ~0.8 m; the hulls funnel floating debris onto the 0.37 m belt), so rows are ~0.65 m apart. A U-turn into a row that close is tighter than the boat can make, so the sweep does every other row first and then comes back for the ones in between; in the simulator that also catches far more drifting litter than a plain lawnmower.
3. The boat follows the rows as one path with algorithm 1. `wp_reached` is sent as it passes each point.
4. After the last point: straight home (the same "come home" as the button).

**Litter moves.** Floating trash drifts with the wind and current, roughly 1-3 % of the wind speed: on a breezy day that's ~0.1 m/s, 60 m in ten minutes. A sweep of a fixed rectangle catches what drifts *through* it while it's being swept, not what was in it when it was drawn (the simulator shows this: `python sim/montecarlo.py --rows 0.8 --currents "0,0;0.05,0.02"`). Plan sweeps across the drift, or sweep where the litter collects: the downwind shore, eddies, the mouth of an inflow.

**Modes.** The boat is always in exactly one of:

| Mode | Meaning | Enters from |
| --- | --- | --- |
| `DRIVEN` | a person steers | Take control (when the link is up) |
| `AUTO` | sweeping the rectangle; the conveyor runs the whole time | Start sweep |
| `COMING_HOME` | heading home (straight after Come home or low battery; along the trail after a lost link); conveyor off | link lost, battery low, outside the fence, or Come home |

Safety transitions fire on the Pi, never on the dashboard, so they work with no laptop connected. Rule of thumb: the dashboard can ask, the boat decides.

**Fence.** In `AUTO` the fence is the sweep rectangle. In `DRIVEN` it is a circle around the station, `DRIVEN_FENCE_M` (150 m, a placeholder until range testing; same number in `boat-pi/config.py` and `ground-station/config.py`). Cross it → stop → `COMING_HOME` (phase `FENCE`) → drive to the nearest point inside (for the circle: 5 m inside, on the straight line toward the station) → back to what it was doing (`AUTO` resumes the sweep; `DRIVEN` hands control back if the link is up). The dashboard warns at 80 % of the way to the edge.

**The map.** Built on the station from the trail and telemetry; the boat doesn't know it exists.
- The fence is split into squares one scoop wide (0.8 m).
- A square is "covered" when the belt went over it: the strip under the boat while the conveyor runs, from every telemetry fix. Driving around with the belt off covers nothing. (GPS error smears the strip by a meter or so; that's the map's honest resolution.)
- Each square keeps the average of the readings taken inside it → heat maps of pH, turbidity, temperature, conductivity.
- Trash pins from the operator pressing a button (or the camera in Level 4).
- Uncovered squares become the next sweep.
- Everything exports to a spreadsheet for the report.

---

## Level 4: sees trash (stretch goal)

Only if Levels 1–3 are done. One wide-angle front camera on the mast, one small rear camera for reversing. Not a ring of cameras: four streams would quadruple the video on the radio and overload the Pi, and the boat sweeps in rows anyway so the sides get covered next row.

Pipeline: frame from the front camera (2–3/s) → small detection model on the Pi → is the box left or right of center → shift the next waypoint ~2 m toward it. Detection never touches the motors directly; it only edits the waypoint list, so all the safety rules stay in one place.

---

## Where the hardware lives (Rev C)

- **Electronics island** (orange box on the arch): Pi, radio, GPS, compass. ~6 × 4 × 3 in dry space with a cable gland. Up high, away from motors, so the compass stays honest.
- **Mast** (12–18 in) on the island for the Wi-Fi antenna.
- **Front camera**: wide-angle, forward, on the mast or front of the island, clear view of the intake. **Rear camera**: small, at the stern.
- **Down in a pontoon**: Arduino, motor drivers, batteries, conveyor gearmotor.

## Power budget (our side)

Roughly 12–15 W continuous: Pi 5–8 W, radio 3–5 W, camera ~1 W, Arduino + sensors 1–2 W. Motors dwarf this. Electrical has it for battery sizing. Two batteries (motors on one, electronics on the other) means a motor stall can't brown out the Pi.

## Open decisions

- Plain Arduino or ESP32 (ESP32 is a bit more powerful, same Arduino code)
- Which Wi-Fi bridge radios
- Ground station power: outlet or battery pack
- Real battery voltage thresholds (from Electrical)
- Test site, which sets the fence size (with Research)
