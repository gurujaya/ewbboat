import time
import threading
from boatlink import Link


def _pair():
    a = Link("station", listen=("127.0.0.1", 0), peer=("127.0.0.1", 0))
    b = Link("boat", listen=("127.0.0.1", 0), peer=("127.0.0.1", 0))
    a.peer = ("127.0.0.1", b._sock.getsockname()[1])
    b.peer = ("127.0.0.1", a._sock.getsockname()[1])
    return a, b


def test_heartbeat_brings_link_up_and_messages_flow():
    a, b = _pair()
    got = []
    b.on("cmd", got.append)
    a.start(); b.start()
    try:
        deadline = time.time() + 2
        while not (a.up and b.up) and time.time() < deadline:
            time.sleep(0.05)
        assert a.up and b.up
        a.send("cmd", {"seq": 1, "throttle": 0.3, "steer": 0, "conveyor": False, "mode": "DRIVEN"})
        a.send("cmd", {"seq": 0, "throttle": 0.9, "steer": 0, "conveyor": False, "mode": "DRIVEN"})  # old seq, dropped
        time.sleep(0.3)
        assert [m["seq"] for m in got] == [1]
    finally:
        a.stop(); b.stop()


def test_link_lost_after_silence():
    a, b = _pair()
    lost = threading.Event()
    b.on_link_lost(lost.set)
    a.start(); b.start()
    try:
        deadline = time.time() + 2
        while not b.up and time.time() < deadline:
            time.sleep(0.05)
        assert b.up
        a.stop()  # station goes silent
        assert lost.wait(5), "link_lost should fire after ~3 s of silence"
        assert not b.up
    finally:
        b.stop()
