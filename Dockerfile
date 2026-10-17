# Runs the simulator (real Arduino firmware logic + real boat-pi + real ground station) in one container.
# This is for a public demo link only. The real station runs on a Pi on shore, not in a cloud.
FROM python:3.12-slim

# A C++ compiler: the sim runs the Arduino firmware's own code (boat-arduino/boat/src),
# compiled for this machine instead of the board.
RUN apt-get update \
    && apt-get install -y --no-install-recommends g++ make \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app
COPY boat-pi/requirements.txt /tmp/req-boat.txt
COPY ground-station/requirements.txt /tmp/req-station.txt
RUN pip install --no-cache-dir -r /tmp/req-boat.txt -r /tmp/req-station.txt

COPY boat-arduino ./boat-arduino
# Build it now (not on first start) so a broken firmware fails the deploy, not the demo.
# rm first: a build/ copied from a Mac would be the wrong kind of binary.
RUN rm -rf boat-arduino/build && make -C boat-arduino host

COPY comms ./comms
COPY boat-pi ./boat-pi
COPY ground-station ./ground-station
COPY sim ./sim
COPY dashboard ./dashboard

ENV PYTHONUNBUFFERED=1 PORT=8080
EXPOSE 8080
# The web port comes from $PORT (Fly: 8080 from fly.toml; Render, Cloud Run, Koyeb set their own;
# Hugging Face Spaces wants 7860). Everything else is the sim's defaults: calm day, 200 m radio
# range, 30 pieces of litter. Add flags here to change the scenario (e.g. "--range", "120").
CMD ["python", "sim/run.py", "--db", "/tmp/station.sqlite"]
