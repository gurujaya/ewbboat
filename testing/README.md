# testing

Owners: **Nicholas Ponce** (`nicholasdponce-del`) and **Mir Amin**. Branch: `testing`.

This is the job that proves the boat works, keeps the parts list honest, and turns the data into the charts that go in the report. Most of it is hands-on and written in markdown and spreadsheets. You don't need to write code to do it well; the pieces where a little code would help are marked *learn-as-you-go*.

## How to edit files without a terminal

1. Go to github.com/gurujaya/ewbboat
2. Top left, switch the branch dropdown from `main` to `testing`
3. Click into `testing/`, click a file, click the pencil icon
4. Edit, then "Commit changes" with a one-line note like `testing: added pool test log Oct 20`

That's a real commit. When a batch of work is done, tell Guru and he'll merge it to `main`.

## What's in here

```
testing/
  parts.md          what the club already has, what we need, prices, links. Feeds PM's BOM.
  calibration.md    how each water sensor was calibrated, the reference used, the numbers, the date
  demo.md           the showcase run-of-show
  logs/             one file per test run: YYYY-MM-DD-what.md
  analysis/         exported CSVs and the charts made from them
```

## The four things this job does

### 1. Parts
Inventory first: ask John, Duncan, and the club what's in the closet (Raspberry Pis, Arduinos, Pi cameras, a gamepad, microSD cards, USB cables, a power bank). Then price what's missing. Keep `parts.md` current; Guru sends it to PM for the BOM and the SGA request.

### 2. Calibration
Each water sensor reads a raw number that has to be matched to a real value:
- **pH:** two or three buffer solutions (pH 4, 7, 10). Read the raw value in each, write both down.
- **Temperature:** against a kitchen or lab thermometer, in cold and warm water.
- **Turbidity:** clear water vs a known standard (or a dilution series of something cloudy).
- **Conductivity:** distilled water vs a known solution (salt water at a measured concentration works).

Write the procedure, the reference, the readings, and the date in `calibration.md`. Guru turns the numbers into code. Redo it if a sensor is swapped.

### 3. Running the tests
`docs/TESTING.md` is the list. For each test: schedule it with the owner of that piece, run it, and the same day write `logs/YYYY-MM-DD-name.md` with:
- date, place, who was there
- what was being tested
- pass or fail
- what you actually saw (numbers, times, distances)
- one photo or screenshot
- if it failed, what you think the cause is

### 4. Data → charts
After each run the dashboard can export a CSV. Put it in `analysis/` and make the charts the report needs:
- battery % over time
- signal strength vs distance from the station
- pH / turbidity / temperature across the pond (a map or at least a table by location)
- how much area was covered and how much trash was picked up

Start in Excel or Google Sheets. *Learn-as-you-go:* a 20-line Python script with `pandas` and `matplotlib` makes the same charts in one command every time. Ask Guru or Zachary for a starter.

### 5. The showcase
`demo.md`: what's on the big screen, who drives, the order of things we show, what we say, and the backup plan if the water test isn't possible that day.

## Who you work with
Everyone: you test their stuff. Especially Eric for range tests, Zachary for the lost-signal and battery tests, Guru for calibration numbers, and PM (Jocelyn, Duncan, Austin) for the BOM and schedule.
