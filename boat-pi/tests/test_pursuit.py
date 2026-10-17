"""PathFollower (pure pursuit) on a perfect little boat: no noise, no current.
Checks the behavior, not the tuning; the sim (sim/headless_test.py) checks the tuning."""

import math

import config
from autopilot import PathFollower
from nav import distance_m, to_latlon, to_xy

HOME = (39.0912, -77.1534)


def ll(x, y):
    """meters east, north of HOME -> lat/lon"""
    return to_latlon((x, y), HOME)


class ToyBoat:
    """Speed follows throttle, turn rate follows the motor difference. 10 Hz."""

    def __init__(self, x, y, heading_deg):
        self.x, self.y, self.h = x, y, heading_deg

    def step(self, left, right, dt=0.1):
        speed = (left + right) / 2 * 1.5
        self.h = (self.h + (left - right) * 60 * dt) % 360
        self.x += speed * math.sin(math.radians(self.h)) * dt
        self.y += speed * math.cos(math.radians(self.h)) * dt

    @property
    def pos(self):
        return ll(self.x, self.y)


def run(follower, boat, seconds=120.0):
    track, t = [], 0.0
    while t < seconds and not follower.done:
        l, r, _ = follower.step(boat.pos, boat.h, t)
        boat.step(l, r)
        track.append((boat.x, boat.y))
        t += 0.1
    return track, t


def test_straight_path_holds_the_line():
    # start 3 m off the line, pointing along it
    f = PathFollower([ll(0, 0), ll(60, 0)])
    boat = ToyBoat(0, 3, 90)
    track, _ = run(f, boat)
    assert f.done
    # once it's had 15 m to get on the line, it stays within 0.3 m of it
    assert max(abs(y) for x, y in track if x > 15) < 0.3
    # and it never crawled: average speed close to cruise
    assert distance_m(boat.pos, ll(60, 0)) < config.ARRIVE_M + 0.5


def test_cruises_without_stopping_at_each_vertex():
    # the same 60 m line, but with a vertex every 3 m (like a trail): no slow-downs
    pts = [ll(x, 0) for x in range(0, 61, 3)]
    f = PathFollower(pts)
    boat = ToyBoat(0, 0, 90)
    _, t = run(f, boat)
    cruise = config.MAX_SPEED * 1.5
    assert t < 60 / cruise + 6        # only the final slow-down costs time


def test_turns_a_corner_and_reports_each_vertex():
    # like AUTO: the path starts at the boat, then the station's waypoints
    pts = [ll(5, 0), ll(30, 0), ll(30, 30)]
    f = PathFollower(pts, start=ll(0, 0))
    boat = ToyBoat(0, 0, 90)
    passed_total, t = 0, 0.0
    indexes = []
    while not f.done and t < 120:
        l, r, passed = f.step(boat.pos, boat.h, t)
        passed_total += passed
        indexes.append(f.next_index)
        boat.step(l, r)
        t += 0.1
    assert f.done
    assert passed_total == len(pts)                  # one per vertex, each exactly once
    assert indexes == sorted(indexes)                # next_index only goes up
    assert abs(boat.x - 30) < 3 and boat.y > 25      # it went up the second leg


def test_done_at_the_end_and_stops():
    f = PathFollower([ll(0, 0), ll(10, 0)])
    boat = ToyBoat(0, 0, 90)
    run(f, boat)
    assert f.done and f.next_index == 2 and f.target is None
    assert f.step(boat.pos, boat.h, 999.0) == (0.0, 0.0, 0)


def test_done_when_past_the_end():
    f = PathFollower([ll(0, 0), ll(10, 0)])
    # the boat is already 2.5 m beyond the end (a gust pushed it): close enough, nothing left to do
    f.step(ll(9, 0), 90.0, 0.0)
    f.step(ll(12.5, 0.5), 90.0, 0.1)
    assert f.done


def test_never_goes_backwards_on_a_folded_path():
    # out 20 m and straight back along the same line (a trail that retraced itself)
    pts = [ll(0, 0), ll(20, 0), ll(20, 1), ll(0, 1)]
    f = PathFollower(pts)
    boat = ToyBoat(0, 0, 90)
    progress = []
    t = 0.0
    while not f.done and t < 120:
        l, r, _ = f.step(boat.pos, boat.h, t)
        progress.append(f.s)
        boat.step(l, r)
        t += 0.1
    assert progress == sorted(progress)
    assert f.done and boat.x < 5          # it went out AND came back


def test_start_point_is_not_a_waypoint():
    # AUTO starts the path at the boat; wp_index still counts the station's list
    f = PathFollower([ll(10, 0), ll(20, 0)], start=ll(0, 0))
    assert f.next_index == 0
    f.step(ll(0.5, 0), 90.0, 0.0)
    assert f.next_index == 0
    assert f.target is not None and abs(to_xy(f.target, HOME)[0] - (0.5 + config.LOOKAHEAD_M)) < 0.1


def test_empty_path_is_done():
    f = PathFollower([])
    assert f.done and f.step(HOME, 0.0, 0.0) == (0.0, 0.0, 0)


class PushedBoat(ToyBoat):
    """A toy boat with a steady current carrying it north at 0.3 m/s."""

    def step(self, left, right, dt=0.1):
        super().step(left, right, dt)
        self.y += 0.3 * dt


def test_learns_to_crab_into_a_side_current():
    # a 90 m row east, with the current pushing north the whole way
    f = PathFollower([ll(0, 0), ll(90, 0)])
    boat = PushedBoat(0, 0, 90)
    track, _ = run(f, boat, seconds=200)
    assert f.done
    early = [abs(y) for x, y in track if 2 < x < 12]
    late = [abs(y) for x, y in track if 40 < x < 85]        # (the last 5 m are the arrival)
    # it starts off being carried off the line, then learns the push and holds the line
    assert max(early) > 0.5
    assert max(late) < 0.1
    # and what it learned points north, where the current pushes
    assert f._drift[1] > 0.5 and abs(f._drift[0]) < 0.5


def test_without_learning_it_holds_a_steady_offset():
    # the same run with the learning switched off: pure pursuit alone sits ~1 m off
    old = config.DRIFT_LEARN_PER_S
    config.DRIFT_LEARN_PER_S = 0.0
    try:
        f = PathFollower([ll(0, 0), ll(90, 0)])
        boat = PushedBoat(0, 0, 90)
        track, _ = run(f, boat, seconds=200)
        late = [abs(y) for x, y in track if x > 60]
        assert min(late) > 0.6
    finally:
        config.DRIFT_LEARN_PER_S = old


def test_carried_past_the_end_it_comes_back():
    # already beyond the last point and 4 m off it (a current carried it wide):
    # not "arrived" yet; it turns and comes back to the point
    f = PathFollower([ll(0, 0), ll(30, 0)])
    boat = ToyBoat(31, 4, 90)
    l, r, _ = f.step(boat.pos, boat.h, 0.0)
    assert not f.done
    run(f, boat, seconds=60)
    assert f.done
    assert distance_m(boat.pos, ll(30, 0)) < 2 * config.ARRIVE_M


class PushedAlongBoat(ToyBoat):
    """A toy boat with a current pushing it ALONG its row (east), 0.3 m/s."""

    def step(self, left, right, dt=0.1):
        super().step(left, right, dt)
        self.x += 0.3 * dt


def test_a_push_along_the_row_is_not_learned_as_sideways():
    f = PathFollower([ll(0, 0), ll(90, 0)])
    boat = PushedAlongBoat(0, 0, 90)
    run(f, boat, seconds=200)
    assert f.done
    assert abs(f._drift[0]) < 0.3 and abs(f._drift[1]) < 0.3   # nothing to learn: no sideways push
