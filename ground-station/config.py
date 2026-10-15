import os

ENV = os.environ.get("BOAT_ENV", "sim")
BOAT_ADDR = (os.environ.get("BOAT_HOST", "127.0.0.1"), int(os.environ.get("BOAT_PORT", "5001")))
STATION_LISTEN = ("0.0.0.0", int(os.environ.get("STATION_PORT", "5000")))
HTTP_PORT = int(os.environ.get("HTTP_PORT", "8000"))
DB_PATH = os.environ.get("STATION_DB", "station.sqlite")

# where the station stands; the map and the grid are built around this
ORIGIN = (float(os.environ.get("ORIGIN_LAT", "39.0912")), float(os.environ.get("ORIGIN_LON", "-77.1534")))

GRID_M = 3.0                 # square size, matches GPS accuracy
DRIVEN_FENCE_M = 150.0       # placeholder until range testing; a box this far around the origin
ROW_SPACING_M = 0.3 * 10     # placeholder for the sim: 3 m rows so a sweep finishes in minutes
CMD_HZ = 10
