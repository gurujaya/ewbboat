# radio-testing

Radios, antennas, and the tests that tell us how far the boat can go. Also the place for working with the Research team on the fence size.

Branch: `radio-testing`.

## What this job owns

- Picking and configuring the boat ↔ station Wi-Fi bridge pair
- Antenna and mast choice with Mechanical (height matters more than anything over water)
- The station's own Wi-Fi for laptops (with the ground-station owner)
- Range tests: signal strength vs distance, written down
- The lost-signal test procedure (`docs/TESTING.md`)
- Later: a LoRa backup link for commands, if we have time

## Layout

```
radio-testing/
  radios.md        which radios we picked and why, settings, addresses, channel
  antenna.md       mast height, cable, placement on the island
  range-test.md    how to run a range test, step by step
  logs/            one file per test: date, place, distance vs dBm, notes
  scripts/         small helpers, e.g. log signal strength from the station every second
```

## Range test, short version

1. Station on its pole on shore, boat on the water (or carried along the shore for a first test).
2. Start the station logging `signal_dbm` and GPS distance once a second.
3. Move the boat out in a straight line, pausing every 25 m.
4. Note where signal drops below −80 dBm and where the link is lost.
5. Write the log to `logs/`, and the distance into `docs/ARCHITECTURE.md` as the DRIVEN fence radius.

Full version in `range-test.md` (to write).
