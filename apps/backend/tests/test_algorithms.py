from itertools import permutations
from time import perf_counter

import pytest

from app.algorithms.mapf import cbs, first_conflict, plan
from app.algorithms.pathfinding import Constraint, Reservations, astar, space_time_astar
from app.domain.grid import Grid, manhattan
from app.domain.models import Cell, Warehouse
from app.scheduling.assignment import hungarian


def grid() -> Grid:
    return Grid(
        Warehouse(id="test", name="Test", width=4, height=4, cells=[Cell(x=1, y=1, type="WALL")])
    )


def test_astar_shortest_and_unreachable() -> None:
    g = grid()
    assert manhattan((0, 0), (3, 2)) == 5
    p = astar(g, (0, 1), (2, 1))
    assert p is not None and len(p) == 5
    assert astar(g, (0, 0), (1, 1)) is None
    assert astar(g, (0, 0), (0, 0)) == [(0, 0)]
    assert all(g.walkable(x) for x in p)


def test_space_time_waits_and_future_goal_constraints() -> None:
    g = grid()
    p = space_time_astar(g, (0, 0), (1, 0), constraints=(Constraint(1, (1, 0)),))
    assert p == [(0, 0), (0, 0), (1, 0)]
    p = space_time_astar(g, (0, 0), (0, 0), constraints=(Constraint(2, (0, 0)),))
    assert p is not None and len(p) >= 4 and p[2] != (0, 0)
    p = space_time_astar(g, (0, 0), (1, 0), constraints=(Constraint(1, edge=((0, 0), (1, 0))),))
    assert p is not None and len(p) == 3


def test_reservations_and_conflicts() -> None:
    reservations = Reservations()
    reservations.reserve([(0, 0), (1, 0)])
    assert not reservations.permits((1, 0), (0, 0), 1)
    assert not reservations.permits((2, 0), (1, 0), 9)
    assert not reservations.safe_to_stay((1, 0), 0)
    vertex = first_conflict({"a": [(0, 0), (1, 0)], "b": [(2, 0), (1, 0)]})
    assert vertex is not None and vertex.vertex == (1, 0)
    edge = first_conflict({"a": [(0, 0), (1, 0)], "b": [(1, 0), (0, 0)]})
    assert edge is not None and edge.a_edge is not None
    assert first_conflict({"a": [(0, 0)], "b": [(2, 0), (1, 0), (0, 0)]}) is not None


@pytest.mark.parametrize("method", ["prioritized", "adaptive", "cbs"])
def test_mapf_collision_free(method: str) -> None:
    result = plan(grid(), {"a": (0, 0), "b": (1, 0)}, {"a": (1, 0), "b": (0, 0)}, method)
    assert result.status == "SUCCESS"
    assert first_conflict(result.paths) is None
    assert result.cost == 8  # detour around the wall at (1,1)
    assert result.optimal == (method == "cbs")


def test_baseline_refuses_conflicting_routes() -> None:
    result = plan(grid(), {"a": (0, 0), "b": (1, 0)}, {"a": (1, 0), "b": (0, 0)}, "astar")
    assert result.status == "CONFLICT"


def test_cbs_limit_is_not_unsolvable() -> None:
    result = cbs(
        grid(),
        {"a": (0, 0), "b": (1, 0)},
        {"a": (1, 0), "b": (0, 0)},
        max_nodes=1,
        deadline=perf_counter() + 10,
    )
    assert result.status == "TIMEOUT" and not result.optimal


@pytest.mark.parametrize("costs", [[[9, 1, 5], [2, 9, 6]], [[9, 1], [2, 9], [3, 5]]])
def test_hungarian_against_exhaustive_matching(costs: list[list[float]]) -> None:
    pairs = hungarian(costs)
    actual = sum(costs[i][j] for i, j in pairs)
    n, m = len(costs), len(costs[0])
    if n <= m:
        expected = min(
            sum(costs[i][j] for i, j in enumerate(js)) for js in permutations(range(m), n)
        )
    else:
        expected = min(
            sum(costs[i][j] for j, i in enumerate(rows)) for rows in permutations(range(n), m)
        )
    assert actual == expected
