"""The UDP link between the boat and the ground station.

One Link per side. It sends a heartbeat 4 times a second, receives in a background
thread, dispatches by message type, ignores old `cmd` packets, and calls you back
when the other side has been silent for too long (and again when it's back).

Hardware-free: in the simulator the same class runs over 127.0.0.1. The only
sim hook is `drop_when`: a function that returns True when the radio is "out of
range", so packets get dropped exactly like a real weak link would drop them.
"""

from __future__ import annotations

import logging
import socket
import threading
import time
from typing import Callable

from .messages import BadMessage, decode, encode

log = logging.getLogger("boatlink")

HEARTBEAT_HZ = 4
LINK_LOST_S = 3.0


class Link:
    def __init__(
        self,
        name: str,
        listen: tuple[str, int],
        peer: tuple[str, int],
        drop_when: Callable[[], bool] | None = None,
    ):
        self.name = name
        self.peer = peer
        self.drop_when = drop_when
        self._sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self._sock.bind(listen)
        self._sock.settimeout(0.25)
        self._handlers: dict[str, list[Callable[[dict], None]]] = {}
        self._on_lost: list[Callable[[], None]] = []
        self._on_back: list[Callable[[], None]] = []
        self._last_heard = 0.0
        self._last_seq = -1
        self._up = False
        self._running = False
        self._threads: list[threading.Thread] = []
        self.lock = threading.Lock()

    # ---- wiring ---------------------------------------------------------
    def on(self, t: str, fn: Callable[[dict], None]) -> None:
        self._handlers.setdefault(t, []).append(fn)

    def on_link_lost(self, fn: Callable[[], None]) -> None:
        self._on_lost.append(fn)

    def on_link_back(self, fn: Callable[[], None]) -> None:
        self._on_back.append(fn)

    # ---- lifecycle ------------------------------------------------------
    def start(self) -> None:
        self._running = True
        for target in (self._recv_loop, self._hb_loop):
            th = threading.Thread(target=target, daemon=True, name=f"{self.name}-{target.__name__}")
            th.start()
            self._threads.append(th)

    def stop(self) -> None:
        self._running = False
        for th in self._threads:
            th.join(timeout=1)
        self._sock.close()

    # ---- state ----------------------------------------------------------
    @property
    def up(self) -> bool:
        return self._up

    def seconds_since_heard(self) -> float:
        return time.time() - self._last_heard if self._last_heard else float("inf")

    # ---- send -----------------------------------------------------------
    def send(self, t: str, body: dict | None = None) -> None:
        if self.drop_when and self.drop_when():
            return
        try:
            self._sock.sendto(encode(t, body), self.peer)
        except OSError as e:
            log.warning("send failed: %s", e)

    # ---- internals ------------------------------------------------------
    def _hb_loop(self) -> None:
        period = 1.0 / HEARTBEAT_HZ
        while self._running:
            self.send("hb", {"from": self.name})
            time.sleep(period)

    def _recv_loop(self) -> None:
        while self._running:
            try:
                data, _ = self._sock.recvfrom(4096)
            except socket.timeout:
                self._check_lost()
                continue
            except OSError:
                break
            if self.drop_when and self.drop_when():
                self._check_lost()
                continue
            try:
                msg = decode(data)
            except BadMessage as e:
                log.warning("bad packet: %s", e)
                continue
            self._heard()
            if msg["t"] == "cmd":
                if msg["seq"] <= self._last_seq:
                    continue
                self._last_seq = msg["seq"]
            for fn in self._handlers.get(msg["t"], []):
                try:
                    fn(msg)
                except Exception:  # a bad handler must not kill the link
                    log.exception("handler for %s failed", msg["t"])

    def _heard(self) -> None:
        self._last_heard = time.time()
        if not self._up:
            self._up = True
            log.info("%s: link up", self.name)
            for fn in self._on_back:
                fn()

    def _check_lost(self) -> None:
        if self._up and self.seconds_since_heard() > LINK_LOST_S:
            self._up = False
            log.info("%s: link lost", self.name)
            for fn in self._on_lost:
                fn()
