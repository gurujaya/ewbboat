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
