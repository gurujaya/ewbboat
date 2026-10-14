# How we work in this repo

Short version: work on your job's branch, open a pull request into `main` when something works, and never push straight to `main`.

## Branches

There is one long-lived branch per job, and they all start from `main`:

| Branch | Job |
| --- | --- |
| `boat-arduino` | Arduino firmware |
| `boat-pi` | Raspberry Pi software on the boat |
| `ground-station` | The station on shore |
| `dashboard` | The web page |
| `radio-testing` | Radios, antenna, range tests |

Work directly on your job's branch. If two people share a job, make a short-lived branch off it named `job/your-name-what-it-is`, for example `boat-pi/guru-trail-points`, and merge it back into the job branch when it works.

`main` is the branch that always works. The only way code gets into `main` is a pull request.

## The loop

```bash
git checkout boat-pi           # your job's branch
git pull                       # get what others pushed
# ... write code ...
git add .
git commit -m "trail: save a point every 3 m with signal strength"
git push
```

When a piece actually works (on the table, in the pool, wherever that piece gets tested), open a pull request from your job branch into `main`. Put in the description:

- what it does
- how you tested it
- anything another job needs to know (a new message field, a changed pin, a new dependency)

One other person reads it and approves. Then merge.

## Commit messages

First word is the area, then what changed. Keep it to one line when you can.

```
arduino: read battery voltage on A0 and send it with telemetry
pi: back up along the trail to the last point with signal > -75 dBm
station: store trail points in sqlite
dashboard: take-control button locks out other viewers
docs: add low-battery thresholds to ARCHITECTURE
```

## Message formats are shared

Anything that goes over the radio or the USB cable is defined in [docs/MESSAGES.md](docs/MESSAGES.md). If you need a new field, change the doc first, in its own pull request, so the boat side and the station side change together. Don't invent a field in code and hope the other side notices.

## Before you push

- It runs. If it's Python, `python -m py_compile yourfile.py` at minimum.
- No secrets, no Wi-Fi passwords, no API keys. Those go in a `.env` or a `*.local.json`, which are ignored.
- No giant files. Logs, videos, and datasets go in the shared OneDrive, not here. If a test log is small and useful, put it in `radio-testing/logs/`.

## Write it down

Every time something works for the first time, write a line in the engineering notebook (OneDrive) and, if it's a setup step others will need, in that job's `README.md`. Documentation is part of the project, not an afterthought.

## Using Claude Code in this repo

The repo has a `CLAUDE.md` that tells Claude Code how the project is laid out and what the rules are, so it can help with any job without being re-explained each time.

```bash
cd ewbboat
git checkout boat-pi      # the job you're working on
claude                    # starts Claude Code in this folder
```

Ask it for things like "implement the heartbeat sender in boat-pi following docs/MESSAGES.md" or "write the unit test for the bearing calculation." It reads `CLAUDE.md`, the docs, and your job's `TASKS.md`, and it should follow the same branch and message rules as everyone else.
