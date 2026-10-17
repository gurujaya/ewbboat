from sweep import plan
from grid import Grid

O = (39.0912, -77.1534)


def n(p, m): return (p[0] + m / 111320.0, p[1])
def e(p, m):
    import math
    return (p[0], p[1] + m / (111320.0 * math.cos(math.radians(p[0]))))


def test_plan_rows_alternate_and_stay_inside():
    corners = [O, n(e(O, 40), 20)]
    pts = plan(corners, row_spacing_m=5, inset_m=2)
    assert len(pts) >= 6 and len(pts) % 2 == 0
    assert pts[0][1] < pts[1][1]          # first row west -> east
    assert pts[2][1] > pts[3][1]          # second row east -> west
    for lat, lon in pts:
        assert O[0] <= lat <= n(O, 20)[0] and O[1] <= lon <= e(O, 40)[1]


def test_plan_empty_when_too_small():
    assert plan([O, n(e(O, 2), 2)], 5) == []


def test_grid_marks_and_averages():
    g = Grid(O, 3.0)
    g.mark(*n(e(O, 4), 4))
    g.reading(*n(e(O, 4), 4), {"ph": 7.0})
    g.reading(*n(e(O, 5), 5), {"ph": 8.0})
    snap = g.snapshot()
    assert len(snap["cells"]) == 1 and snap["cells"][0]["ix"] == 1 and snap["cells"][0]["iy"] == 1
    assert abs(snap["cells"][0]["ph"] - 7.5) < 1e-9
    assert g.coverage_pct([O, n(e(O, 6), 6)]) == 25.0


def test_plan_every_other_row_first():
    corners = [O, n(e(O, 40), 20)]
    pts = plan(corners, row_spacing_m=4, inset_m=2, turn_rows=2)
    lats = [pts[i][0] for i in range(0, len(pts), 2)]       # one lat per row, in visiting order
    assert len(lats) == 5
    assert lats[:3] == sorted(lats[:3]) and lats[3:] == sorted(lats[3:])   # 0,2,4 then 1,3
    assert lats[0] < lats[3] < lats[1]
    assert sorted(lats) == sorted(set(lats))                 # every row exactly once
    for i in range(0, len(pts) - 2, 2):
        assert (pts[i][1] < pts[i + 1][1]) != (pts[i + 2][1] < pts[i + 3][1])   # direction alternates


def test_swath_paints_a_strip_as_wide_as_the_scoop():
    g = Grid(O, 0.8)
    # heading east along a line 10.2 m north of the origin (a square boundary is at 10.4 m, so
    # the 0.8 m strip, 9.8..10.6, straddles two rows of squares), fixes 0.2 m apart for 4 m
    for k in range(21):
        g.mark_swath(*n(e(O, 10 + 0.2 * k), 10.2), heading_deg=90.0, width_m=0.8)
    cells = g.covered
    iys = {iy for ix, iy in cells}
    assert iys == {12, 13}                                   # the strip is 0.8 m tall: two rows of squares
    assert min(ix for ix, iy in cells) == 12 and max(ix for ix, iy in cells) == 17   # 10..14 m east
    # nothing marked a boat-length away
    assert all(abs(iy - 12) <= 1 for ix, iy in cells)


def test_sweep_must_fit_inside_the_driving_fence():
    from sweep import corners_inside_circle
    assert corners_inside_circle([O, n(e(O, 40), 20)], O, 150)
    assert not corners_inside_circle([O, n(e(O, 160), 20)], O, 150)       # one corner 160 m out
    assert not corners_inside_circle([n(O, 100), n(e(O, 100), 120)], O, 150)   # 141 m corner ok, (100,120) = 156 m not
