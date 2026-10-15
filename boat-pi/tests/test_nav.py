import math
from nav import wrap_deg, distance_m, bearing_deg, go_to_waypoint, mix, inside_rect, clamp_to_rect

HOME = (39.0912, -77.1534)


def north_of(p, m):
    return (p[0] + m / 111320.0, p[1])


def east_of(p, m):
    return (p[0], p[1] + m / (111320.0 * math.cos(math.radians(p[0]))))


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


def test_go_to_waypoint_turns_right_when_target_is_right():
    target = east_of(HOME, 50)          # bearing 90
    l, r, arrived = go_to_waypoint(HOME, 0.0, target, kp=0.01, max_speed=0.6, slow_radius_m=10, arrive_m=2)
    assert not arrived
    assert l > r                        # left faster -> turns right


def test_go_to_waypoint_turns_left_across_the_360_seam():
    target = east_of(HOME, -50)         # bearing 270
    l, r, _ = go_to_waypoint(HOME, 10.0, target, kp=0.01, max_speed=0.6, slow_radius_m=10, arrive_m=2)
    assert r > l                        # needs to turn left, not spin 280 degrees right


def test_go_to_waypoint_arrives_and_slows():
    far = north_of(HOME, 100)
    near = north_of(HOME, 5)
    lf, rf, _ = go_to_waypoint(HOME, 0.0, far, kp=0.01, max_speed=0.6, slow_radius_m=10, arrive_m=2)
    ln, rn, _ = go_to_waypoint(HOME, 0.0, near, kp=0.01, max_speed=0.6, slow_radius_m=10, arrive_m=2)
    assert abs(lf - 0.6) < 1e-6 and abs(rf - 0.6) < 1e-6
    assert ln < lf
    _, _, arrived = go_to_waypoint(HOME, 0.0, north_of(HOME, 1), kp=0.01, max_speed=0.6, slow_radius_m=10, arrive_m=2)
    assert arrived


def test_mix_clamps():
    assert mix(1.0, 1.0) == (1.0, 0.0)
    assert mix(0.5, 0.0) == (0.5, 0.5)
    assert mix(-0.5, 0.0) == (-0.5, -0.5)


def test_rect():
    box = [HOME, north_of(east_of(HOME, 100), 100)]
    assert inside_rect(north_of(east_of(HOME, 50), 50), box)
    assert not inside_rect(north_of(HOME, 150), box)
    c = clamp_to_rect(north_of(HOME, 150), box, margin_m=3)
    assert inside_rect(c, box)
    assert abs(distance_m(c, north_of(east_of(HOME, 3), 97))) < 1.0
