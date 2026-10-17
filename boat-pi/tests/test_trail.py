import math

from trail import Trail

HOME = (39.0912, -77.1534)


def n(p, m):
    return (p[0] + m / 111320.0, p[1])


def e(p, m):
    return (p[0], p[1] + m / (111320.0 * math.cos(math.radians(p[0]))))


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
    # the trail is a straight line north, so the cleaned-up path is just its two ends
    assert len(back) == 2
    assert t.path_home()[-1] == HOME
    # backing up goes from the newest point back to the good one, by the trail
    to_good = t.path_back_to(good)
    assert to_good[0] == (t.points[-1].lat, t.points[-1].lon)
    assert to_good[-1] == (good.lat, good.lon)
    # cleaning up the path never touches the trail itself
    assert len(t.points) == len(sigs)


def test_path_home_keeps_the_corners():
    t = Trail(3, 5)
    pts = [n(HOME, 0), n(HOME, 10), n(HOME, 20), e(n(HOME, 20), 10), e(n(HOME, 20), 20)]
    for i, p in enumerate(pts):
        t.maybe_add(p, -50, now=i * 10)
    home = t.path_home()
    assert home[0] == pts[-1] and home[-1] == HOME
    assert pts[2] in home                       # the corner survives


def test_last_good_falls_back_to_home_when_nothing_good():
    t = Trail(3, 5)
    t.maybe_add(HOME, -95, now=0)
    t.maybe_add(n(HOME, 10), -95, now=10)
    assert t.last_good(-75).i == 0


def test_home_is_the_average_of_the_first_fixes():
    t = Trail(every_m=3, every_s=5, home_settle_s=3)
    # four noisy fixes around HOME while the boat sits at the jetty
    assert t.maybe_add(n(HOME, 1.0), -50, now=0) is None
    assert t.maybe_add(n(HOME, -1.0), -52, now=1) is None
    assert t.maybe_add(e(HOME, 0.8), -54, now=2) is None
    p = t.maybe_add(e(HOME, -0.8), -56, now=3)
    assert p is not None and p.i == 0
    assert math.hypot((p.lat - HOME[0]) * 111320, (p.lon - HOME[1]) * 111320 * 0.777) < 0.01
    assert p.signal_dbm == -53
    assert t.home == (p.lat, p.lon)
    assert len(t.points) == 1


def test_home_settles_early_if_the_boat_drives_off():
    t = Trail(every_m=3, every_s=5, home_settle_s=3)
    assert t.maybe_add(HOME, -50, now=0) is None
    p = t.maybe_add(n(HOME, 4), -50, now=0.5)     # moved 4 m before 3 s were up
    assert p is not None and p.i == 0
    assert len(t.points) == 1



def test_come_home_goes_straight_and_lost_link_retraces():
    import config
    from safety import HomePlan
    t = Trail(3, 5)
    # out from home, then a little lawnmower east/west: the trail is a long zigzag
    for i, p in enumerate([HOME, n(HOME, 10), n(HOME, 20)]):
        t.maybe_add(p, -50, now=i)
    rows = [e(n(HOME, 20 + r * 3), 30 if r % 2 == 0 else 0) for r in range(4)]
    for i, p in enumerate(rows):
        t.maybe_add(p, -60 - 10 * i, now=10 + i)         # the signal fades along the rows: -60, -70, -80, -90
    here = (t.points[-1].lat, t.points[-1].lon)
    plan = HomePlan()
    plan.start_home(t, "come_home", here)
    assert plan.phase == "DIRECT"
    assert plan.runner.points == [HOME]                  # one leg: straight to the launch point
    # a lost link backs up along the trail instead
    plan2 = HomePlan()
    plan2.start_link_lost(now=100.0)
    assert plan2.phase == "WAIT"
    l, r, ev = plan2.step(here, 0.0, t, link_up=False, now=100.0 + config.LINK_LOST_WAIT_S)
    assert ev == "backing_up" and plan2.phase == "BACKUP"
    assert len(plan2.runner.points) >= 2                 # the trail, not a straight line
