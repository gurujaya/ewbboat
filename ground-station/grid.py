"""The map: squares the boat has covered, and the average reading in each."""

from __future__ import annotations

import math
from collections import defaultdict

M_PER_DEG_LAT = 111_320.0


class Grid:
    def __init__(self, origin: tuple[float, float], size_m: float):
        self.origin = origin
        self.size = size_m
        self.cos = math.cos(math.radians(origin[0]))
        self.covered: set[tuple[int, int]] = set()
        self.sums: dict[tuple[int, int], dict[str, list[float]]] = defaultdict(lambda: defaultdict(lambda: [0.0, 0]))
        self.trash: list[tuple[float, float]] = []

    def cell(self, lat: float, lon: float) -> tuple[int, int]:
        x = (lon - self.origin[1]) * M_PER_DEG_LAT * self.cos
        y = (lat - self.origin[0]) * M_PER_DEG_LAT
        return int(math.floor(x / self.size)), int(math.floor(y / self.size))

    def mark(self, lat: float, lon: float) -> None:
        self.covered.add(self.cell(lat, lon))

    def mark_swath(self, lat: float, lon: float, heading_deg: float, width_m: float) -> None:
        """The belt passed here: mark every square under a strip width_m wide across the
        boat's heading. Called for each telemetry fix while the conveyor runs (5 a second,
        ~0.2 m apart), which paints a continuous strip."""
        h = math.radians(heading_deg)
        # across the heading: east component cos(h), north -sin(h)
        ax, ay = math.cos(h), -math.sin(h)
        n = max(2, int(width_m / (self.size * 0.5)) + 1)
        for i in range(n):
            d = -width_m / 2 + width_m * i / (n - 1)
            dlat = d * ay / M_PER_DEG_LAT
            dlon = d * ax / (M_PER_DEG_LAT * self.cos)
            self.covered.add(self.cell(lat + dlat, lon + dlon))

    def reading(self, lat: float, lon: float, water: dict | None) -> None:
        if not water:
            return
        c = self.cell(lat, lon)
        for k, v in water.items():
            if v is not None:
                s = self.sums[c][k]
                s[0] += v
                s[1] += 1

    def snapshot(self) -> dict:
        cells = []
        for c in self.covered:
            avg = {k: (s[0] / s[1] if s[1] else None) for k, s in self.sums.get(c, {}).items()}
            cells.append({"ix": c[0], "iy": c[1], **avg})
        return {"size_m": self.size, "origin": self.origin, "cells": cells, "trash": self.trash}

    def coverage_pct(self, corners: list[tuple[float, float]] | None) -> float | None:
        if not corners:
            return None
        c0 = self.cell(min(c[0] for c in corners), min(c[1] for c in corners))
        c1 = self.cell(max(c[0] for c in corners) - 1e-9, max(c[1] for c in corners) - 1e-9)  # exclusive top edge
        total = (c1[0] - c0[0] + 1) * (c1[1] - c0[1] + 1)
        inside = sum(1 for (ix, iy) in self.covered if c0[0] <= ix <= c1[0] and c0[1] <= iy <= c1[1])
        return 100.0 * inside / total if total else None
