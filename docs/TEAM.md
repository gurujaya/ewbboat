# Who does what

Six people, six jobs. Each person has a branch with the same name as their job. Your branch is your workspace: commit there as often as you like. When something works, open a pull request into `main`.

| Person | GitHub | Branch | Job in one line |
| --- | --- | --- | --- |
| Guru Jayaprakash | `gurujaya` | `boat-arduino`, `ground-station` | Arduino firmware, the station server, the message spec, merging to `main` |
| Eric Cheguen Mendez | `echeguen` | `comms` | Boat ↔ ground station link: the `boatlink` library both sides use, heartbeat, the radios, range tests |
| Zachary Kamba | `zachkam1` | `boat-pi` | The boat's brain in Python: trail points, modes, lost-signal and battery rules, the autopilot |
| Sebastian Norberte | `SebastianNorberte` | `dashboard` | The web page: video, map, readings, gamepad driving |
| Nicholas Ponce | `nicholasdponce-del` | `testing` | Parts and BOM, sensor calibration, running and logging tests, charts for the report, showcase demo |
| Mir Amin | (send Guru your GitHub) | `testing` | Same job as Nicholas; split the list between you |

Pairs: Guru and Zachary pair on the Pi ↔ Arduino serial link. Eric and Guru pair on the station side of the link. Nicholas and Mir run tests with whoever owns the thing being tested.

## Guru — `boat-arduino` and `ground-station`

- **Arduino:** motors, conveyor, the 4 sensors, GPS, compass, battery, and the 2-second watchdog. Get the pin list from John (Electrical).
- **Ground station:** the always-on Pi on shore: SQLite, the FastAPI server, serving the dashboard, the sweep planner, the coverage grid.
- Owns `docs/MESSAGES.md`. Reviews every pull request into `main`.
- Start: `boat-arduino/TASKS.md`, `ground-station/TASKS.md`

## Eric — `comms`

The boat and the station talk over a radio. Eric owns everything about that conversation.

- **`comms/boatlink/`**: a small Python package both the boat Pi and the station import. It opens the UDP socket, encodes and decodes the JSON messages from `docs/MESSAGES.md`, sends the heartbeat 4×/s, and tells the caller "link lost" after 3 s of silence. Write it once, both sides use it.
- **Radios:** pick the Wi-Fi bridge pair with the team, configure them, fixed addresses, write it up in `comms/radios.md`.
- **Antenna and mast** with Mechanical.
- **Range tests** on land and water, logged in `comms/logs/`. The range number becomes the fence size.
- **Lost-signal test** with Zachary (cut the station radio on purpose).
- Start: `comms/TASKS.md`. Read `docs/MESSAGES.md` first; it's the contract you're implementing.

## Zachary — `boat-pi`

All Python. The Pi is the brain of the boat.

- Serial to the Arduino (with Guru), camera stream, CSV logging.
- Uses Eric's `boatlink` for the radio; doesn't write socket code.
- **Trail points** every 3 m / 5 s with signal strength.
- **Modes** (`DRIVEN`, `AUTO`, `COMING_HOME`) and every safety rule: lost signal, low battery, fence.
- **Algorithm 1** (go to a waypoint) and running a waypoint list for the sweep.
- Unit tests for the math (bearing, wrap, last-good-point).
- Start: `boat-pi/TASKS.md`, then `docs/ARCHITECTURE.md` Levels 2 and 3.

## Sebastian — `dashboard`

HTML, CSS, and plain JavaScript. No framework, no build step.

- Live video panel, readings strip, battery, signal, mode.
- Map with the boat marker, the trail, the fence, and later the coverage overlay and heat map.
- Gamepad → commands at 10×/s, Take control lock, keyboard fallback.
- Buttons: Start sweep, Come home, Export CSV, Mark trash.
- Can be built entirely against the station's `--fake-boat` mode, no hardware needed.
- Start: `dashboard/TASKS.md`

## Nicholas and Mir — `testing`

No coding required for most of this, and it's work the project can't ship without. You work in markdown files and spreadsheets, straight from the GitHub website if you want (edit a file, write a one-line description, "Commit changes"). Learn-as-you-go pieces are marked.

- **Parts.** Inventory what the club already has (Pis, Arduinos, cameras, gamepad, SD cards). Price what's missing. Keep `testing/parts.md` current; it feeds PM's BOM.
- **Calibration.** Each water sensor needs calibrating against a known reference (pH buffer solutions, a turbidity standard, a thermometer). Follow the procedure, record the numbers in `testing/calibration.md`. Guru puts the numbers into the Arduino.
- **Run the tests.** `docs/TESTING.md` lists every test. For each one: set it up with the owner, run it, write the result in `testing/logs/` the same day (date, who, pass/fail, what you saw, a photo).
- **Data → charts.** After each run, export the CSV from the dashboard and make the charts for the report: battery over time, signal vs distance, pH across the pond. Start in Excel/Sheets; a Python plotting script is the learn-as-you-go step if you want it.
- **Engineering notebook.** Make sure every "it worked for the first time" moment gets written down.
- **Showcase demo.** The run-of-show for the day: what's on the screen, who drives, what we say.
- Start: `testing/TASKS.md`

## If you're new to git

```bash
git clone https://github.com/gurujaya/ewbboat.git
cd ewbboat
git checkout comms            # your branch name from the table
# edit files
git add .
git commit -m "comms: first draft of radios.md"
git push
```

Or skip the terminal: open the repo on github.com, switch to your branch with the dropdown at the top left, click a file, click the pencil, edit, "Commit changes." That's a real commit, same as the terminal.

More in [`../CONTRIBUTING.md`](../CONTRIBUTING.md).
