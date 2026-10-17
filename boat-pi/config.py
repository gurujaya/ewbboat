"""Every number the boat's behavior depends on, in one place, with units.

Pick an environment with BOAT_ENV=sim|bench|boat (default sim). The sim env is
set up by sim/run.py; bench and boat are what you edit when the hardware arrives.
"""

import os

ENV = os.environ.get("BOAT_ENV", "sim")

# ---- serial to the Arduino ------------------------------------------------
SERIAL_PORT = os.environ.get("BOAT_SERIAL", {"sim": "/tmp/boat-serial", "bench": "/dev/ttyUSB0", "boat": "/dev/ttyUSB0"}[ENV])
SERIAL_BAUD = 115200

# ---- radio ------------------------------------------------------------------
STATION_ADDR = (os.environ.get("STATION_HOST", "127.0.0.1"), int(os.environ.get("STATION_PORT", "5000")))
BOAT_LISTEN = ("0.0.0.0", int(os.environ.get("BOAT_PORT", "5001")))
SIGNAL_DROP_DBM = -88          # in the sim, packets drop below this; real radios just go quiet

# ---- loop timing ------------------------------------------------------------
LOOP_HZ = 10
TELEMETRY_HZ = 5              # tlm to the station; matches the Arduino's 5 Hz T lines (GPS + compass)
CMD_STALE_S = 1.0              # no cmd for this long while DRIVEN -> motors to zero

# ---- trail ------------------------------------------------------------------
TRAIL_EVERY_M = 3.0
TRAIL_EVERY_S = 5.0
HOME_SETTLE_S = 3.0            # average the first fixes this long before calling that spot "home"
GOOD_SIGNAL_DBM = -75          # a trail point with signal above this counts as "good"

# ---- lost signal ------------------------------------------------------------
LINK_LOST_WAIT_S = 10.0        # stop and wait this long before backing up

# ---- battery ----------------------------------------------------------------
BATT_WARN_PCT = 30
BATT_HOME_PCT = 20
BATT_CUT_PCT = 10
BATT_AVG_S = 5.0

# ---- navigation -------------------------------------------------------------
# Path following (pure pursuit, autopilot.py). Tuned in the sim; re-tune in the pool.
# Loop gain and the wag. steer -> yaw rate has ~0.4 s of lag on this hull, and the compass
# arrives 5 times a second. With KP 0.015 the heading loop was close to its stability limit
# and the nose wagged ~11 deg/s on straight rows; 0.008 is well damped (8 deg/s, most of what's
# left is GPS jitter) and holds the rows just as well. sim/montecarlo.py measures this ("sway").
# Lesson from the sim: do NOT try to calm the wag by smoothing (STEER_SMOOTH_S, HEADING_SMOOTH_S):
# lag in a loop this close to its limit makes it oscillate MORE (11 -> 15-20 deg/s). Lower the gain.
KP = 0.008                     # steer per degree of heading error
KD = 0.001                     # steer per deg/s the error is changing; damps the swing after a turn.
                               # In the sim it makes no measurable difference (the turn already settles
                               # quickly); it's here for the pool, where a heavier hull may overshoot.
BEARING_SMOOTH_S = 0.0         # low-pass the bearing to the aim point with this time constant (0 = off; tried
                               # 0.5 in the sim: a little less wag, slightly worse rows; not worth it).
                               # Two loops are nested here: a slow one (where am I vs the path -> which
                               # way to point) and a fast one (which way to point -> motors). The GPS
                               # jitter enters through the slow one, so that's where to smooth it; the
                               # fast loop keeps its full speed. A big change (a turn) is not smoothed.
STEER_SMOOTH_S = 0.0           # low-pass the steering command with this time constant (0 = off).
                               # The GPS position still jitters a little after the filter; seen from
                               # LOOKAHEAD_M ahead that's a few degrees of heading-error flicker 5 times
                               # a second, which the P term turns into a constant wag. The hull can't
                               # follow that anyway, so don't ask it to.
LOOKAHEAD_M = 3.0              # aim at the point this far ahead along the path.
                               # shorter: hugs the line but wiggles; longer: smooth but cuts corners.
                               # Sim: 3 m held rows best (2.5-6 m tried)
# Learning the push of the current (autopilot.py). Pure pursuit on its own holds a steady
# offset in a side current (it aims 3 m ahead on the line, so it only crabs as much as that
# geometry allows: ~1 m off in a 0.3 m/s cross current). So the follower slowly adds up how
# far, and which way, the boat sits off its path, and moves its aim point the other way.
DRIFT_LEARN_PER_S = 0.15       # aim shift (m) added per second per meter of offset
DRIFT_SHIFT_MAX_M = 3.0        # the aim never moves more than this off the path
DRIFT_FORGET_S = 90.0          # what was learned fades with this time constant, so a push picked up
                               # on one stretch doesn't linger for the rest of the trip
ARRIVE_M = 2.0                 # within this of the path's last point = done (GPS is good to ~2-3 m)
MAX_SPEED = 0.6                # cruise, as a fraction of full throttle, in AUTO and COMING_HOME
SLOW_RADIUS_M = 5.0            # ease off only within this of the path's LAST point

HEADING_SMOOTH_S = 0.0         # low-pass the compass heading with this time constant (0 = off; see the
                               # note above KP: smoothing here made the wag worse in the sim)

# GPS position filter (nav.PositionFilter)
FILTER_ALPHA = 0.25            # how much each new fix moves the position (0..1). 0.4 tracked a bit
                               # tighter but let more jitter through to the steering (more wag)
FILTER_BETA = 0.04             # how much each new fix moves the velocity
FILTER_GAP_RESET_S = 2.0       # no fix for this long: forget the velocity and start over
FILTER_JUMP_M = 15.0           # a fix this far from where we expected is ignored (3 in a row: start over)

# Trail clean-up before following it home (nav.simplify). The raw trail is kept as is.
TRAIL_SIMPLIFY_M = 1.0         # wiggles smaller than this are smoothed out
TRAIL_MIN_GAP_M = 1.5          # points closer than this to the previous one are dropped

# ---- fences -----------------------------------------------------------------
# Where the station stands. Same env vars and defaults as ground-station/config.py.
ORIGIN = (float(os.environ.get("ORIGIN_LAT", "39.0912")), float(os.environ.get("ORIGIN_LON", "-77.1534")))
DRIVEN_FENCE_M = 150.0         # in DRIVEN, stay within this of the station. Same as ground-station/config.py;
                               # placeholder until range testing
FENCE_RETURN_INSIDE_M = 5.0    # after crossing the driving fence, go back to a point this far inside

# ---- logging ----------------------------------------------------------------
LOG_DIR = os.environ.get("BOAT_LOG_DIR", "logs")
