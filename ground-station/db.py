"""SQLite. One table per message type. Save first, then everything else."""

from __future__ import annotations

import json
import sqlite3
import threading
import time

SCHEMA = """
CREATE TABLE IF NOT EXISTS runs (id INTEGER PRIMARY KEY, started REAL, note TEXT);
CREATE TABLE IF NOT EXISTS tlm (id INTEGER PRIMARY KEY, run INTEGER, ts REAL, lat REAL, lon REAL, heading REAL,
  batt_pct REAL, signal REAL, mode TEXT, temp REAL, ph REAL, turb REAL, cond REAL, raw TEXT);
CREATE TABLE IF NOT EXISTS trail (id INTEGER PRIMARY KEY, run INTEGER, ts REAL, i INTEGER, lat REAL, lon REAL, signal REAL);
CREATE TABLE IF NOT EXISTS evt (id INTEGER PRIMARY KEY, run INTEGER, ts REAL, kind TEXT, detail TEXT);
CREATE TABLE IF NOT EXISTS ack (id INTEGER PRIMARY KEY, run INTEGER, ts REAL, for_ TEXT, ok INTEGER, msg TEXT);
CREATE TABLE IF NOT EXISTS sweeps (id INTEGER PRIMARY KEY, run INTEGER, ts REAL, sweep_id TEXT, corners TEXT, points TEXT);
"""


class DB:
    def __init__(self, path: str):
        self.conn = sqlite3.connect(path, check_same_thread=False)
        self.conn.executescript(SCHEMA)
        self.lock = threading.Lock()
        with self.lock:
            cur = self.conn.execute("INSERT INTO runs(started, note) VALUES (?, ?)", (time.time(), ""))
            self.run = cur.lastrowid
            self.conn.commit()

    def save(self, m: dict) -> None:
        t = m["t"]
        with self.lock:
            if t == "tlm":
                w = m.get("water") or {}
                self.conn.execute(
                    "INSERT INTO tlm(run,ts,lat,lon,heading,batt_pct,signal,mode,temp,ph,turb,cond,raw) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)",
                    (self.run, m["ts"], m["lat"], m["lon"], m["heading_deg"], m["batt_pct"], m.get("signal_dbm"), m["mode"],
                     w.get("temp_c"), w.get("ph"), w.get("turb_ntu"), w.get("cond_us"), json.dumps(m)),
                )
            elif t == "trail":
                self.conn.execute("INSERT INTO trail(run,ts,i,lat,lon,signal) VALUES (?,?,?,?,?,?)",
                                  (self.run, m["ts"], m["i"], m["lat"], m["lon"], m.get("signal_dbm")))
            elif t == "evt":
                self.conn.execute("INSERT INTO evt(run,ts,kind,detail) VALUES (?,?,?,?)", (self.run, m["ts"], m["kind"], m.get("detail", "")))
            elif t == "ack":
                self.conn.execute("INSERT INTO ack(run,ts,for_,ok,msg) VALUES (?,?,?,?,?)", (self.run, m["ts"], m["for"], int(m["ok"]), m.get("msg", "")))
            self.conn.commit()

    def save_sweep(self, sweep_id: str, corners, points) -> None:
        with self.lock:
            self.conn.execute("INSERT INTO sweeps(run,ts,sweep_id,corners,points) VALUES (?,?,?,?,?)",
                              (self.run, time.time(), sweep_id, json.dumps(corners), json.dumps(points)))
            self.conn.commit()

    def tlm_rows(self, run: int | None = None) -> list[dict]:
        run = self.run if run is None else run
        with self.lock:
            cur = self.conn.execute("SELECT ts,lat,lon,heading,batt_pct,signal,mode,temp,ph,turb,cond FROM tlm WHERE run=? ORDER BY ts", (run,))
            cols = [d[0] for d in cur.description]
            return [dict(zip(cols, r)) for r in cur.fetchall()]

    def recent(self, table: str, n: int = 200) -> list[dict]:
        with self.lock:
            cur = self.conn.execute(f"SELECT * FROM {table} WHERE run=? ORDER BY id DESC LIMIT ?", (self.run, n))
            cols = [d[0] for d in cur.description]
            return [dict(zip(cols, r)) for r in reversed(cur.fetchall())]
