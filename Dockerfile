# Runs the simulator (fake Arduino + real boat-pi + real ground station) in one container.
# This is for a public demo link only. The real station runs on a Pi on shore, not in a cloud.
FROM python:3.12-slim

WORKDIR /app
COPY boat-pi/requirements.txt /tmp/req-boat.txt
COPY ground-station/requirements.txt /tmp/req-station.txt
RUN pip install --no-cache-dir -r /tmp/req-boat.txt -r /tmp/req-station.txt

COPY comms ./comms
COPY boat-pi ./boat-pi
COPY ground-station ./ground-station
COPY sim ./sim
COPY dashboard ./dashboard

ENV PYTHONUNBUFFERED=1
EXPOSE 8080
# --http 8080 is what Fly expects; everything else is defaults (200 m radio range, gentle current)
CMD ["python", "sim/run.py", "--http", "8080", "--db", "/tmp/station.sqlite"]
