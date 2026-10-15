from trail import Trail

HOME = (39.0912, -77.1534)


def n(p, m):
    return (p[0] + m / 111320.0, p[1])


def test_adds_by_distance_and_time():
    t = Trail(every_m=3, every_s=5)
    assert t.maybe_add(HOME, -50, now=0) is not None
    assert t.maybe_add(n(HOME, 1), -50, now=1) is None        # too close, too soon
    assert t.maybe_add(n(HOME, 4), -50, now=2) is not None    # moved 3 m
    assert t.maybe_add(n(HOME, 4.5), -50, now=8) is not None  # 5 s passed
    assert len(t.points) == 3


def test_last_good_and_path_back():
    t = Trail(3, 5)
    sigs = [-50, -55, -60, -70, -80, -90, None]
    for i, s in enumerate(sigs):
        t.maybe_add(n(HOME, i * 10), s, now=i * 10)
    good = t.last_good(-75)
    assert good.i == 3                          # -70 is the last above -75
    back = t.path_back_from(good)
    assert back[0] == (good.lat, good.lon)
    assert back[-1] == HOME
    assert len(back) == 4
    assert t.path_home()[-1] == HOME


def test_last_good_falls_back_to_home_when_nothing_good():
    t = Trail(3, 5)
    t.maybe_add(HOME, -95, now=0)
    t.maybe_add(n(HOME, 10), -95, now=10)
    assert t.last_good(-75).i == 0
