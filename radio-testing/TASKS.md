# radio-testing tasks

## Phase 1
- [ ] Shortlist 2–3 outdoor Wi-Fi bridge pairs with prices; pick one with the team
- [ ] Confirm mast height and antenna spot on the island with Mechanical (Rev C)
- [ ] Write `radios.md` with the choice and why

## Phase 2: table
- [ ] Configure both bridges; boat and station on one network with fixed addresses
- [ ] Measure signal strength from the station side; make it readable by `ground-station/link.py`
- [ ] Help set up the station's own Wi-Fi (hostapd) with the station owner
- [ ] Indoor test: dashboard works through both radios, not the lab Wi-Fi

## Phase 3: water
- [ ] Write `range-test.md`
- [ ] `scripts/log_signal.py`: distance vs dBm once a second
- [ ] Range test on land along the shore; log it
- [ ] Range test on the water; log it; write the fence radius into ARCHITECTURE
- [ ] Run the lost-signal test with the boat-pi owner (cut the station radio on purpose)
- [ ] Note what the antenna height change does to range (try two heights)

## Phase 4
- [ ] Stretch: LoRa pair as a slow backup for `cmd` and `hb`; document in `radios.md`

## Always
- [ ] Every test gets a file in `logs/` the same day
