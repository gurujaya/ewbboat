"""Assemble the static site for GitHub Pages / Vercel: the viewer, plus the Python files the
in-browser simulator needs, plus a root page that forwards to the viewer.

    python sim/browser/build_site.py site      # writes ./site
"""

from __future__ import annotations

import os
import shutil
import sys

ROOT = os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", ".."))
PY_FILES = [
    "boat-pi/config.py", "boat-pi/main.py", "boat-pi/modes.py", "boat-pi/nav.py", "boat-pi/autopilot.py",
    "boat-pi/safety.py", "boat-pi/trail.py",
    "comms/boatlink/__init__.py", "comms/boatlink/messages.py", "comms/boatlink/link.py",
    "ground-station/config.py", "ground-station/main.py", "ground-station/db.py", "ground-station/grid.py", "ground-station/sweep.py",
    "sim/physics.py", "sim/browser/core.py",
]


def main() -> None:
    out = os.path.abspath(sys.argv[1] if len(sys.argv) > 1 else "site")
    if os.path.isdir(out):
        shutil.rmtree(out)
    shutil.copytree(os.path.join(ROOT, "sim", "viewer"), os.path.join(out, "viewer"))
    for f in PY_FILES:
        dst = os.path.join(out, "py", f)
        os.makedirs(os.path.dirname(dst), exist_ok=True)
        shutil.copy2(os.path.join(ROOT, f), dst)
    with open(os.path.join(out, "index.html"), "w") as fh:
        fh.write('<!doctype html><meta charset="utf-8"><meta http-equiv="refresh" content="0; url=viewer/">'
                 '<title>EWB boat</title><a href="viewer/">Open the boat</a>\n')
    with open(os.path.join(out, ".nojekyll"), "w") as fh:   # GitHub Pages: serve folders as they are
        fh.write("")
    n = sum(len(fs) for _, _, fs in os.walk(out))
    print(f"site: {n} files in {out}")


if __name__ == "__main__":
    main()
