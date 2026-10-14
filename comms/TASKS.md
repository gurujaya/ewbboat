# comms tasks

Owner: Eric. Tick in the same commit that finishes the work.

## Phase 1: pick and plan
- [ ] Read `docs/MESSAGES.md` end to end; ask Guru about anything unclear
- [ ] Shortlist 2–3 outdoor Wi-Fi bridge pairs with prices; pick one with the team; write `radios.md`
- [ ] Confirm mast height and antenna spot on the island with Mechanical (Rev C); write `antenna.md`
- [ ] Agree ports and the boat's fixed address with Guru and Zachary; put them in `radios.md`

## Phase 2: the library, on a table
- [ ] `boatlink/messages.py`: encode/decode for `cmd`, `hb`, `tlm`, `trail`, `wps`, `ack`, `evt`; reject bad input
- [ ] `boatlink/link.py`: UDP socket, `send()`, receive thread, dispatch by `t`, ignore `cmd` with an older `seq`
- [ ] `boatlink/heartbeat.py`: send `hb` 4×/s; `on_link_lost` after 3 s; `on_link_back`
- [ ] `boatlink/signal.py`: read dBm from the radio (start with `iw dev wlan0 link`; fall back to None)
- [ ] `tests/`: round-trip every message type; seq ordering; link-lost at exactly 3 s with a fake clock
- [ ] Two laptops on the lab Wi-Fi: `hb` both ways, `cmd` one way, `tlm` back
- [ ] Configure both bridge radios; boat Pi and station Pi on them with fixed addresses
- [ ] Same test through the real radios, not the lab Wi-Fi
- [ ] Hand `boatlink` to Guru and Zachary; help them wrap it

## Phase 3: water
- [ ] Write `range-test.md`
- [ ] `scripts/log_signal.py`
- [ ] Range test on land along the shore; log it
- [ ] Range test on the water; log it; write the fence radius into `docs/ARCHITECTURE.md`
- [ ] Try two antenna heights; log what it does to range
- [ ] Lost-signal test with Zachary: cut the station radio, boat must come back
- [ ] Measure video's share of the link; decide if we need to lower resolution

## Phase 4 (stretch)
- [ ] LoRa pair as a slow backup for `cmd` and `hb`; same `Link` interface; document in `radios.md`

## Always
- [ ] Every test gets a file in `logs/` the same day
- [ ] Any message field change goes through `docs/MESSAGES.md` first
