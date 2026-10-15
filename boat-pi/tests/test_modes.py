from modes import Modes, DRIVEN, AUTO, COMING_HOME


def test_start_sweep_needs_link_battery_and_points():
    m = Modes()
    assert not m.request(AUTO, "start_sweep", link_up=False, batt_pct=90, have_waypoints=True).ok
    assert not m.request(AUTO, "start_sweep", link_up=True, batt_pct=25, have_waypoints=True).ok
    assert not m.request(AUTO, "start_sweep", link_up=True, batt_pct=90, have_waypoints=False).ok
    assert m.request(AUTO, "start_sweep", link_up=True, batt_pct=90, have_waypoints=True).ok
    assert m.mode == AUTO


def test_safety_always_wins_and_resume_returns_to_previous():
    m = Modes()
    m.request(AUTO, "start_sweep", link_up=True, batt_pct=90, have_waypoints=True)
    ch = m.request(COMING_HOME, "link_lost", link_up=False, batt_pct=90)
    assert ch.ok and m.mode == COMING_HOME
    ch = m.resume_previous()
    assert ch.ok and m.mode == AUTO


def test_cannot_leave_coming_home_on_low_battery():
    m = Modes()
    m.request(COMING_HOME, "batt_low", link_up=True, batt_pct=15)
    assert not m.request(DRIVEN, "take_control", link_up=True, batt_pct=15).ok
    assert m.request(DRIVEN, "take_control", link_up=True, batt_pct=25).ok


def test_coming_home_to_auto_must_go_through_driven():
    m = Modes()
    m.request(COMING_HOME, "come_home", link_up=True, batt_pct=90)
    assert not m.request(AUTO, "start_sweep", link_up=True, batt_pct=90, have_waypoints=True).ok
