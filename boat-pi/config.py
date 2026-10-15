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
TELEMETRY_HZ = 1
CMD_STALE_S = 1.0              # no cmd for this long while DRIVEN -> motors to zero

# ---- trail ------------------------------------------------------------------
TRAIL_EVERY_M = 3.0
TRAIL_EVERY_S = 5.0
GOOD_SIGNAL_DBM = -75          # a trail point with signal above this counts as "good"

# ---- lost signal ------------------------------------------------------------
LINK_LOST_WAIT_S = 10.0        # stop and wait this long before backing up

# ---- battery ----------------------------------------------------------------
BATT_WARN_PCT = 30
BATT_HOME_PCT = 20
BATT_CUT_PCT = 10
BATT_AVG_S = 5.0

# ---- navigation -------------------------------------------------------------
KP = 0.01                      # steer per degree of heading error; tune in the pool
ARRIVE_M = 2.0
MAX_SPEED = 0.6                # of full throttle, while in AUTO or COMING_HOME
SLOW_RADIUS_M = 10.0           # start slowing down this far from the target

# ---- logging ----------------------------------------------------------------
LOG_DIR = os.environ.get("BOAT_LOG_DIR", "logs")
