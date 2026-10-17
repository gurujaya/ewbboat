import math
import random

from nav import (
    PositionFilter, bearing_deg, clamp_to_rect, distance_m, inside_circle, inside_rect, mix,
    path_lengths, point_at, point_inside_circle, project_on_path, pursuit_command, simplify,
    to_latlon, to_xy, wrap_deg,
)

HOME = (39.0912, -77.1534)


def north_of(p, m):
    return (p[0] + m / 111320.0, p[1])


def east_of(p, m):
    return (p[0], p[1] + m / (111320.0 * math.cos(math.radians(p[0]))))


# ---- basics -------------------------------------------------------------------


def test_wrap():
    assert wrap_deg(350) == -10
    assert wrap_deg(-190) == 170
    assert wrap_deg(180) == 180
    assert wrap_deg(0) == 0


def test_distance_and_bearing_cardinal():
    assert abs(distance_m(HOME, north_of(HOME, 100)) - 100) < 0.5
    assert abs(distance_m(HOME, east_of(HOME, 100)) - 100) < 0.5
    assert abs(bearing_deg(HOME, north_of(HOME, 50)) - 0) < 0.1
    assert abs(bearing_deg(HOME, east_of(HOME, 50)) - 90) < 0.1
    assert abs(bearing_deg(HOME, north_of(HOME, -50)) - 180) < 0.1
    assert abs(bearing_deg(HOME, east_of(HOME, -50)) - 270) < 0.1


def test_local_frame_round_trip():
    p = north_of(east_of(HOME, 30), -12)
    x, y = to_xy(p, HOME)
    assert abs(x - 30) < 0.01 and abs(y + 12) < 0.01
    back = to_latlon((x, y), HOME)
    assert distance_m(back, p) < 0.001


def test_mix_clamps():
    assert mix(1.0, 1.0) == (1.0, 0.0)
    assert mix(0.5, 0.0) == (0.5, 0.5)
    assert mix(-0.5, 0.0) == (-0.5, -0.5)


# ---- pursuit_command: the steering rule --------------------------------------------


def test_pursuit_turns_toward_the_target():
    l, r = pursuit_command(30.0, 0.0, 50.0, kp=0.01, kd=0.0, max_speed=0.6, slow_radius_m=5)
    assert l > r                        # target to the right -> left motor faster -> turns right
    l, r = pursuit_command(-30.0, 0.0, 50.0, kp=0.01, kd=0.0, max_speed=0.6, slow_radius_m=5)
    assert r > l


def test_pursuit_heading_error_across_the_360_seam():
    # nose at 10 degrees, target bearing 270: turn left 100 degrees, not right 260
    err = wrap_deg(270 - 10)
    l, r = pursuit_command(err, 0.0, 50.0, kp=0.01, kd=0.0, max_speed=0.6, slow_radius_m=5)
    assert r > l


def test_pursuit_cruises_and_only_slows_at_the_end_or_when_pointing_off():
    l, r = pursuit_command(0.0, 0.0, 50.0, kp=0.01, kd=0.0, max_speed=0.6, slow_radius_m=5)
    assert abs(l - 0.6) < 1e-9 and abs(r - 0.6) < 1e-9        # full cruise, no slowing mid-path
    l2, _ = pursuit_command(0.0, 0.0, 2.0, kp=0.01, kd=0.0, max_speed=0.6, slow_radius_m=5)
    assert 0.6 * 0.3 - 1e-9 <= l2 < 0.6                        # eases off near the end, but never crawls to 0
    l3, r3 = pursuit_command(90.0, 0.0, 50.0, kp=0.01, kd=0.0, max_speed=0.6, slow_radius_m=5)
    assert (l3 + r3) / 2 < 0.3                                 # way off: turn first


def test_pursuit_d_term_damps_the_swing():
    # error 10 deg to the right but shrinking fast: steer less than P alone would
    lp, rp = pursuit_command(10.0, 0.0, 50.0, kp=0.01, kd=0.002, max_speed=0.6, slow_radius_m=5)
    ld, rd = pursuit_command(10.0, -30.0, 50.0, kp=0.01, kd=0.002, max_speed=0.6, slow_radius_m=5)
    assert (ld - rd) < (lp - rp)


# ---- path geometry ---------------------------------------------------------------------


def test_path_lengths_and_point_at():
    path = [(0.0, 0.0), (10.0, 0.0), (10.0, 5.0)]
    cum = path_lengths(path)
    assert cum == [0.0, 10.0, 15.0]
    assert point_at(path, cum, 4.0) == (4.0, 0.0)
    assert point_at(path, cum, 12.0) == (10.0, 2.0)
    assert point_at(path, cum, 99.0) == (10.0, 5.0)
    assert point_at(path, cum, -1.0) == (0.0, 0.0)


def test_project_finds_progress_and_never_goes_back():
    path = [(0.0, 0.0), (20.0, 0.0)]
    cum = path_lengths(path)
    s, d, past = project_on_path(path, cum, (7.0, 1.5), 0.0, 50.0)
    assert abs(s - 7.0) < 1e-9 and abs(d - 1.5) < 1e-9 and not past
    # the boat drifted back; progress stays where it was
    s2, _, _ = project_on_path(path, cum, (3.0, 0.5), s, 50.0)
    assert s2 == s
    # beyond the end
    _, _, past = project_on_path(path, cum, (21.0, 0.3), 15.0, 50.0)
    assert past


def test_project_does_not_jump_to_a_row_beyond_the_window():
    # a lawnmower: row 1 east, 3 m up, row 2 west. The boat is near the start of
    # row 1 but drifted toward row 2. It must not skip ahead to row 2.
    path = [(0.0, 0.0), (30.0, 0.0), (30.0, 3.0), (0.0, 3.0)]
    cum = path_lengths(path)
    s, _, _ = project_on_path(path, cum, (5.0, 2.0), 3.0, 6.0)
    assert 3.0 <= s <= 9.0


# ---- trail clean-up ----------------------------------------------------------------------


def test_simplify_straightens_wiggles_and_keeps_corners():
    rng = random.Random(1)
    # 30 m east with +-0.4 m wiggle, then a corner, 20 m north
    pts = [north_of(east_of(HOME, i), rng.uniform(-0.4, 0.4)) for i in range(0, 31, 3)]
    corner = east_of(HOME, 30)
    pts += [north_of(corner, j) for j in range(3, 21, 3)]
    out = simplify(pts, tolerance_m=1.0)
    assert out[0] == pts[0] and out[-1] == pts[-1]
    assert len(out) <= 4                              # start, corner (one or two points), end
    assert any(distance_m(p, corner) < 1.5 for p in out)


def test_simplify_drops_bunched_points():
    pts = [HOME] + [north_of(HOME, 0.2 * k) for k in range(1, 6)] + [north_of(east_of(HOME, 10), 10)]
    out = simplify(pts, tolerance_m=0.01, min_gap_m=1.5)
    assert out == [HOME, pts[-1]]


def test_simplify_short_lists_unchanged():
    assert simplify([], 1.0) == []
    assert simplify([HOME], 1.0) == [HOME]
    assert simplify([HOME, north_of(HOME, 1)], 1.0) == [HOME, north_of(HOME, 1)]


# ---- fences ---------------------------------------------------------------------------------


def test_rect():
    box = [HOME, north_of(east_of(HOME, 100), 100)]
    assert inside_rect(north_of(east_of(HOME, 50), 50), box)
    assert not inside_rect(north_of(HOME, 150), box)
    c = clamp_to_rect(north_of(HOME, 150), box, margin_m=3)
    assert inside_rect(c, box)
    assert abs(distance_m(c, north_of(east_of(HOME, 3), 97))) < 1.0


def test_circle_fence_and_the_way_back_inside():
    assert inside_circle(north_of(HOME, 149), HOME, 150)
    assert not inside_circle(east_of(HOME, 151), HOME, 150)
    out = north_of(east_of(HOME, 120), 120)               # ~170 m out, to the north-east
    back = point_inside_circle(out, HOME, 150, margin_m=5)
    assert abs(distance_m(HOME, back) - 145) < 0.1        # 5 m inside the edge
    assert abs(bearing_deg(HOME, back) - bearing_deg(HOME, out)) < 0.1   # straight toward the station
    inside = north_of(HOME, 50)
    assert point_inside_circle(inside, HOME, 150) == inside


# ---- position filter ---------------------------------------------------------------------------


def _track(seconds, hz, speed_mps, noise_m, seed=3):
    """A boat going north at a steady speed, with jittery GPS. Yields (t, true, fix)."""
    rng = random.Random(seed)
    for k in range(int(seconds * hz)):
        t = k / hz
        true = north_of(HOME, speed_mps * t)
        fix = north_of(east_of(true, rng.gauss(0, noise_m)), rng.gauss(0, noise_m))
        yield t, true, fix


def test_filter_converges_on_a_straight_track():
    f = PositionFilter()
    for t, true, fix in _track(20, 5, 1.0, 0.0):
        f.update(t, fix)
    assert abs(f.speed_mps() - 1.0) < 0.02
    assert abs(wrap_deg(f.course_deg() - 0.0)) < 1.0
    assert distance_m(f.position(t), true) < 0.05
    # predicts between fixes: 0.1 s later the boat is 0.1 m further north
    assert abs(distance_m(f.position(t + 0.1), north_of(true, 0.1))) < 0.05


def test_filter_cuts_noise():
    f = PositionFilter()
    raw_err, filt_err = [], []
    for t, true, fix in _track(60, 5, 1.0, 0.5):
        f.update(t, fix)
        if t > 5:
            raw_err.append(distance_m(fix, true))
            filt_err.append(distance_m(f.position(t), true))
    rms = lambda xs: math.sqrt(sum(x * x for x in xs) / len(xs))
    assert rms(filt_err) < 0.7 * rms(raw_err)
    assert abs(f.speed_mps() - 1.0) < 0.3


def test_filter_speed_needs_a_second_of_fixes():
    f = PositionFilter()
    assert f.position(0.0) is None and f.speed_mps() is None and not f.ready
    f.update(0.0, HOME)
    f.update(0.4, north_of(HOME, 0.4))
    assert f.ready and f.speed_mps() is None
    f.update(1.0, north_of(HOME, 1.0))
    assert f.speed_mps() is not None


def test_filter_ignores_a_repeated_fix():
    f = PositionFilter()
    for t, _, fix in _track(5, 5, 1.0, 0.0):
        f.update(t, fix)
    v = f.speed_mps()
    f.update(t + 0.2, fix)                 # the Arduino sent the same fix again
    assert f.speed_mps() == v


def test_filter_resets_after_a_dropout():
    f = PositionFilter(gap_reset_s=2.0)
    for t, _, fix in _track(10, 5, 1.0, 0.0):
        f.update(t, fix)
    assert f.speed_mps() > 0.9
    # 5 s with no fix, then a fix somewhere else: start over, no stale velocity
    there = east_of(HOME, 40)
    f.update(t + 5.0, there)
    assert distance_m(f.position(t + 5.0), there) < 0.01
    assert f.speed_mps() is None
    # an explicit reset (fix lost) forgets everything
    f.reset()
    assert not f.ready and f.position(t + 6.0) is None


def test_filter_ignores_one_wild_fix_but_follows_a_real_jump():
    f = PositionFilter(jump_m=15.0)
    for t, _, fix in _track(10, 5, 1.0, 0.0):
        f.update(t, fix)
    good = f.position(t)
    f.update(t + 0.2, east_of(fix, 200))  # one glitch, 200 m off
    assert distance_m(f.position(t + 0.2), north_of(good, 0.2)) < 0.5
    # three in a row: the GPS really is somewhere else; believe it
    far = east_of(HOME, 300)
    for k in range(1, 4):
        f.update(t + 0.2 + 0.2 * k, north_of(far, 0.01 * k))
    assert distance_m(f.position(t + 0.8), far) < 1.0
