import pytest
from boatlink.messages import encode, decode, BadMessage


def test_round_trip_every_type():
    samples = {
        "cmd": {"seq": 1, "throttle": 0.5, "steer": -0.2, "conveyor": True, "mode": "DRIVEN"},
        "hb": {"from": "boat"},
        "tlm": {"lat": 39.1, "lon": -77.1, "heading_deg": 90.0, "batt_pct": 80, "mode": "AUTO"},
        "trail": {"i": 3, "lat": 39.1, "lon": -77.1, "signal_dbm": -60},
        "wps": {"id": "s1", "points": [[39.1, -77.1], [39.2, -77.2]]},
        "ack": {"for": "s1", "ok": True},
        "evt": {"kind": "link_lost"},
    }
    for t, body in samples.items():
        msg = decode(encode(t, body))
        assert msg["t"] == t
        assert "ts" in msg
        for k, v in body.items():
            assert msg[k] == v


def test_rejects_unknown_type():
    with pytest.raises(BadMessage):
        encode("nope", {})


def test_rejects_missing_field():
    with pytest.raises(BadMessage):
        encode("cmd", {"seq": 1})


def test_rejects_out_of_range_throttle():
    with pytest.raises(BadMessage):
        encode("cmd", {"seq": 1, "throttle": 2.0, "steer": 0, "conveyor": False, "mode": "DRIVEN"})


def test_rejects_garbage():
    with pytest.raises(BadMessage):
        decode(b"not json")
    with pytest.raises(BadMessage):
        decode(b"[1,2,3]")
