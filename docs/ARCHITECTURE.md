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
| Telemetry | boat → station | GPS, heading, battery, signal, 4 water readings | ~1/s |
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

**Trail points.** Every ~3 m or every 5 s (whichever comes first) the Pi saves a point:

```
{ lat, lon, time, signal_dbm }
```

The list of points is the trail. It is also sent to the station so the dashboard can draw it.

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

**Algorithm 1: go to one waypoint.** The whole autopilot.

```
every 100 ms:
  pos, heading = read GPS, compass
  dist    = distance(pos, target)            # meters
  bearing = atan2(dlon * cos(lat), dlat)     # 0..360, clockwise from north
  error   = wrap(bearing - heading)          # -180..180
  steer   = Kp * error                       # start Kp ~ 0.01
  speed   = min(0.6, dist / 10)              # slow down near the point
  send(left = speed + steer, right = speed - steer)
  if dist < 2 m: target = next waypoint
```

`Kp` is the only knob: too small it wanders, too big it zigzags. Tune it in the pool. 2 m "arrived" radius because GPS is only good to ~3 m. Current is handled for free: pushed sideways → error grows → it steers back.

**Algorithm 2: sweep (lawnmower / boustrophedon).**
1. Operator draws a rectangle on the dashboard map. Its corners are also the fence.
2. The station turns it into a numbered list of waypoints, row by row, alternating direction. Row spacing ≈ 0.8 × conveyor width (Rev C conveyor is 14.6 in → ~12 in → ~0.3 m) so GPS error and current don't leave gaps.
3. The boat runs algorithm 1 on each point.
4. After the last point: follow the trail home. Or, if battery allows, sweep the squares it missed.

**Modes.** The boat is always in exactly one of:

| Mode | Meaning | Enters from |
| --- | --- | --- |
| `DRIVEN` | a person steers | Take control (when the link is up) |
| `AUTO` | sweeping the rectangle | Start sweep |
| `COMING_HOME` | following the trail home | link lost, battery low, outside the fence, or Come home |

Safety transitions fire on the Pi, never on the dashboard, so they work with no laptop connected. Rule of thumb: the dashboard can ask, the boat decides.

**Fence.** In `AUTO` the fence is the sweep rectangle. In `DRIVEN` it is the radius from range testing. Cross it in any mode → stop → drive to the nearest point inside. The dashboard warns at 80 % of the way to the edge.

**The map.** Built on the station from the trail and telemetry; the boat doesn't know it exists.
- The fence is split into 3 m squares (matching GPS accuracy).
- A square is "covered" when a trail point lands in it.
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
