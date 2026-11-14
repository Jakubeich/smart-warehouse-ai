"""Independent joint-state Dijkstra oracle for tiny stay-at-goal MAPF problems."""

import random
from heapq import heappop, heappush
from itertools import product

from app.algorithms.mapf import plan
from app.domain.grid import Grid, manhattan
from app.domain.models import Cell, Point, Warehouse


def oracle(grid: Grid, starts: tuple[Point, ...], goals: tuple[Point, ...]) -> int | None:
    # A robot may declare final arrival at a goal; then it must stay forever.
    # Edges cost the number of agents not yet finalized, yielding sum of arrival times.
    queue = [(0, starts, 0)]
    distance = {(starts, 0): 0}
    full = (1 << len(starts)) - 1
    while queue:
        cost, positions, finished = heappop(queue)
        if cost != distance[(positions, finished)]:
            continue
        if finished == full:
            return cost
        for i, p in enumerate(positions):
            if p == goals[i] and not finished & (1 << i):
                mask = finished | (1 << i)
                key = (positions, mask)
                if cost < distance.get(key, 10**9):
                    distance[key] = cost
                    heappush(queue, (cost, positions, mask))
        options = [
            [p] if finished & (1 << i) else [p, *grid.neighbors(p)] for i, p in enumerate(positions)
        ]
        for new in product(*options):
            if len(set(new)) != len(new):
                continue
            if any(
                positions[i] == new[j] and positions[j] == new[i]
                for i in range(len(new))
                for j in range(i + 1, len(new))
            ):
                continue
            new_cost = cost + len(starts) - finished.bit_count()
            key = (new, finished)
            if new_cost < distance.get(key, 10**9):
                distance[key] = new_cost
                heappush(queue, (new_cost, new, finished))
    return None


def test_cbs_cost_matches_independent_oracle() -> None:
    g = Grid(
        Warehouse(
            id="tiny",
            name="Tiny",
            width=4,
            height=4,
            cells=[
                Cell(x=x, y=y, type="WALL") for x in range(4) for y in range(4) if x >= 3 or y >= 2
            ],
        )
    )
    rng = random.Random(891)
    free = [(x, y) for x in range(3) for y in range(2)]
    for _ in range(24):
        starts = tuple(rng.sample(free, 2))
        goals = tuple(rng.sample(free, 2))
        expected = oracle(g, starts, goals)
        result = plan(
            g,
            dict(zip(["a", "b"], starts)),
            dict(zip(["a", "b"], goals)),
            "cbs",
            timeout=5,
            max_nodes=10000,
        )
        assert result.status == "SUCCESS"
        assert result.optimal and result.cost == expected
        for rid, path in result.paths.items():
            assert path[-1] == dict(zip(["a", "b"], goals))[rid]
            assert all(manhattan(a, b) <= 1 for a, b in zip(path, path[1:]))
