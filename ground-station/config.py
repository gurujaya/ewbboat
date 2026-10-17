import os

ENV = os.environ.get("BOAT_ENV", "sim")
BOAT_ADDR = (os.environ.get("BOAT_HOST", "127.0.0.1"), int(os.environ.get("BOAT_PORT", "5001")))
STATION_LISTEN = ("0.0.0.0", int(os.environ.get("STATION_PORT", "5000")))
HTTP_PORT = int(os.environ.get("HTTP_PORT", "8000"))
DB_PATH = os.environ.get("STATION_DB", "station.sqlite")

# where the station stands; the map and the grid are built around this
ORIGIN = (float(os.environ.get("ORIGIN_LAT", "39.0912")), float(os.environ.get("ORIGIN_LON", "-77.1534")))

# The boat scoops a strip about as wide as the gap between its pontoons (Rev C: ~0.8 m; the belt
# itself is 0.37 m, the hulls funnel into it). The map and the sweep are both built on that width.
SCOOP_WIDTH_M = 0.8
GRID_M = SCOOP_WIDTH_M       # a map square is one scoop wide: "covered" means the belt went over it
DRIVEN_FENCE_M = 150.0       # placeholder until range testing; a box this far around the origin
# Sweep rows 0.8 x the scoop width apart, so GPS error and current don't leave gaps between rows.
# Override for a quick demo: ROW_SPACING_M=3 sweeps 5x faster and catches about a quarter.
ROW_SPACING_M = float(os.environ.get("ROW_SPACING_M", str(round(0.8 * SCOOP_WIDTH_M, 2))))
# Rows a boat-width apart need a U-turn tighter than the boat can make, so the sweep does every
# other row first and then comes back for the ones in between (sweep.plan). In the simulator that
# also caught far more drifting litter than a plain lawnmower (sim/montecarlo.py --turn-rows).
SWEEP_TURN_ROWS = 2
CMD_HZ = 10
