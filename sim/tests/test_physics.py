"""Pure checks on physics.py: the boat and the floating trash.

    cd sim && python -m pytest -q
"""

import math

from physics import TRASH_KINDS, BoatPhysics, TrashPiece, World

DT = 0.05


def run(boat: BoatPhysics, seconds: float) -> None:
    for _ in range(int(seconds / DT)):
        boat.step(DT)


def drive(boat: BoatPhysics, seconds: float, left: float, right: float, conveyor: bool) -> None:
    boat.set_motors(left, right, conveyor)
    run(boat, seconds)


def calm_world(**kw) -> World:
    """No current, so a piece stays where the test put it."""
    return World(current_mps=(0.0, 0.0), **kw)


# ---- the boat -----------------------------------------------------------------


def test_moored_boat_does_not_move():
    boat = BoatPhysics(World())   # default current pushes east
    x0, y0 = boat.x, boat.y
    run(boat, 30)
    assert boat.moored
    assert (boat.x, boat.y) == (x0, y0)


def test_speed_builds_and_coasts():
    boat = BoatPhysics(calm_world())
    drive(boat, 0.5, 1.0, 1.0, False)
    early = boat.speed_mps
    assert 0 < early < boat.MAX_SPEED * 0.8, "takes a few seconds to get up to speed"
    run(boat, 10)
    # just under MAX_SPEED: the right thruster is 4 % weaker, so "both at full" isn't quite full push
    assert math.isclose(boat.speed_mps, boat.MAX_SPEED, rel_tol=0.05)
    boat.set_motors(0.0, 0.0, False)
    run(boat, 1)
    assert 0.2 < boat.speed_mps < boat.MAX_SPEED, "coasts: not stopped after one second"
    run(boat, 30)
    assert boat.speed_mps < 0.02, "but it does come to rest"


def test_no_trash_when_asked():
    boat = BoatPhysics(World(trash_count=0))
    assert boat.trash == [] and boat.trash_total == 0 and boat.collected_count == 0
    drive(boat, 5, 0.5, 0.5, True)   # nothing to collect, nothing to crash on


# ---- where the trash spawns ---------------------------------------------------


def test_trash_spawns_in_the_water_and_spaced_out():
    world = World()
    boat = BoatPhysics(world)
    assert boat.trash_total == 30
    sx, sy = world.start_xy
    for p in boat.trash:
        assert isinstance(p, TrashPiece)
        assert p.kind in TRASH_KINDS
        assert not p.collected and p.collected_t is None
        assert boat.TRASH_Y_MIN_M <= p.y <= boat.TRASH_Y_MAX_M
        assert -boat.TRASH_X_MAX_M <= p.x <= boat.TRASH_X_MAX_M
        assert math.hypot(p.x - sx, p.y - sy) >= boat.TRASH_LAUNCH_CLEAR_M
    for a in boat.trash:
        for b in boat.trash:
            if a.id != b.id:
                assert math.hypot(a.x - b.x, a.y - b.y) >= boat.TRASH_SPACING_M
    assert sorted(p.id for p in boat.trash) == list(range(1, 31))


def test_trash_is_seeded_and_repeatable():
    a = BoatPhysics(World(seed=3))
    b = BoatPhysics(World(seed=3))
    c = BoatPhysics(World(seed=4))
    assert [(p.x, p.y, p.kind) for p in a.trash] == [(p.x, p.y, p.kind) for p in b.trash]
    assert [(p.x, p.y) for p in a.trash] != [(p.x, p.y) for p in c.trash]
    run(a, 20)
    run(b, 20)
    assert [(p.x, p.y) for p in a.trash] == [(p.x, p.y) for p in b.trash]


def test_trash_count_does_not_change_the_boats_noise():
    """--trash 0 must leave GPS and compass numbers exactly as before."""
    a = BoatPhysics(World(trash_count=0))
    b = BoatPhysics(World(trash_count=30))
    assert [a.gps() for _ in range(5)] == [b.gps() for _ in range(5)]
    assert a.compass_deg() == b.compass_deg()


# ---- how the trash moves ------------------------------------------------------


def test_trash_drifts_with_the_current():
    boat = BoatPhysics(World(current_mps=(0.2, 0.0)))   # steady push east
    before = [(p.x, p.y) for p in boat.trash]
    run(boat, 60)   # boat still moored: only the water moves
    for (x0, y0), p in zip(before, boat.trash):
        moved_east = p.x - x0
        # ~90 % of the current, which itself gusts between ~55 % and ~145 % of average
        assert 0.2 * 0.9 * 60 * 0.5 < moved_east < 0.2 * 0.9 * 60 * 1.5
        assert abs(p.y - y0) < 2.0, "the random wander is tiny"


def test_trash_never_drifts_onto_the_beach():
    boat = BoatPhysics(World(current_mps=(0.0, -0.5)))   # a strong push south, towards the shore
    run(boat, 300)
    for p in boat.trash:
        assert p.y >= boat.SHORE_Y_M


# ---- collecting ---------------------------------------------------------------


def piece_at(boat: BoatPhysics, ahead_m: float, side_m: float) -> TrashPiece:
    """Put one piece at (ahead, side) in the boat's frame and make it the only trash."""
    h = math.radians(boat.heading_deg)
    x = boat.x + ahead_m * math.sin(h) + side_m * math.cos(h)
    y = boat.y + ahead_m * math.cos(h) - side_m * math.sin(h)
    boat.trash[:] = [TrashPiece(id=1, x=x, y=y, kind="bottle")]
    return boat.trash[0]


def moving_boat() -> BoatPhysics:
    """A boat already at cruise, pointing north, on calm water, with no trash yet."""
    boat = BoatPhysics(calm_world(trash_count=0))
    drive(boat, 10, 0.6, 0.6, False)
    assert boat.speed_mps > 0.5
    return boat


def test_piece_in_the_funnel_is_collected_with_the_belt_on():
    boat = moving_boat()
    p = piece_at(boat, 0.5, 0.0)
    assert boat.in_funnel(p.x, p.y)
    boat.set_motors(0.6, 0.6, True)
    boat.step(DT)
    assert p.collected and p.collected_t == boat.t
    assert boat.collected_count == 1 and boat.trash_total == 1


def test_piece_in_the_funnel_is_not_collected_with_the_belt_off():
    boat = moving_boat()
    p = piece_at(boat, 0.5, 0.0)
    boat.set_motors(0.6, 0.6, False)
    boat.step(DT)
    assert not p.collected


def test_piece_in_the_funnel_is_not_collected_by_a_stopped_boat():
    boat = BoatPhysics(calm_world(trash_count=0))
    boat.moored = False
    p = piece_at(boat, 0.5, 0.0)
    boat.set_motors(0.0, 0.0, True)   # belt on, props off, boat at rest
    boat.step(DT)
    assert not p.collected


def test_piece_one_meter_to_the_side_is_missed():
    boat = moving_boat()
    p = piece_at(boat, 0.5, 1.0)
    assert not boat.in_funnel(p.x, p.y)
    boat.set_motors(0.6, 0.6, True)
    boat.step(DT)
    assert not p.collected


def test_piece_behind_the_boat_is_missed():
    boat = moving_boat()
    p = piece_at(boat, -0.5, 0.0)
    boat.set_motors(0.6, 0.6, True)
    boat.step(DT)
    assert not p.collected


def test_funnel_follows_the_heading():
    """Heading east: a piece 0.5 m east of the boat is dead ahead, one 0.5 m north is beside it."""
    boat = moving_boat()
    boat.heading_deg = 90.0
    assert boat.in_funnel(boat.x + 0.5, boat.y)
    assert not boat.in_funnel(boat.x, boat.y + 0.5)


def test_collected_piece_stops_drifting():
    boat = BoatPhysics(World(current_mps=(0.3, 0.0), trash_count=0))
    drive(boat, 10, 0.6, 0.6, False)
    p = piece_at(boat, 0.5, 0.0)
    boat.set_motors(0.6, 0.6, True)
    boat.step(DT)
    assert p.collected
    x, y = p.x, p.y
    run(boat, 30)
    assert (p.x, p.y) == (x, y)


def test_driving_through_a_piece_picks_it_up():
    """The slow way: a piece 5 m ahead, belt on, drive at it. It must land in the basket."""
    boat = BoatPhysics(calm_world(trash_count=0))
    boat.moored = False
    p = piece_at(boat, 5.0, 0.0)
    # a touch more on the right so the 4 % weaker thruster doesn't curve the boat off the line
    drive(boat, 15, 0.6, 0.625, True)
    assert p.collected and boat.collected_count == 1
