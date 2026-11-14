"""Deterministic A* and space-time A*. Paths include their initial position."""

from dataclasses import dataclass, field
from heapq import heappop, heappush
from itertools import count
from time import perf_counter

from app.domain.grid import Grid, manhattan
from app.domain.models import Point


class PlanningTimeout(Exception):
    pass


@dataclass(frozen=True)
class Constraint:
    time: int
    vertex: Point | None = None
    edge: tuple[Point, Point] | None = None


@dataclass
class Reservations:
    vertices: set[tuple[Point, int]] = field(default_factory=set)
    edges: set[tuple[Point, Point, int]] = field(default_factory=set)
    permanent: dict[Point, int] = field(default_factory=dict)

    def reserve(self, path: list[Point]) -> None:
        for t, p in enumerate(path):
            self.vertices.add((p, t))
            if t:
                self.edges.add((path[t - 1], p, t))
        self.permanent[path[-1]] = len(path) - 1

    def permits(self, a: Point, b: Point, t: int) -> bool:
        return (
            (b, t) not in self.vertices
            and (b, a, t) not in self.edges
            and not (b in self.permanent and t >= self.permanent[b])
        )

    def safe_to_stay(self, goal: Point, t: int) -> bool:
        return goal not in self.permanent and not any(
            p == goal and time >= t for p, time in self.vertices
        )


def astar(grid: Grid, start: Point, goal: Point) -> list[Point] | None:
    if not grid.walkable(start) or not grid.walkable(goal):
        return None
    serial = count()
    frontier = [(manhattan(start, goal), 0, next(serial), start)]
    g_score = {start: 0}
    parent: dict[Point, Point] = {}
    while frontier:
        _, g, _, current = heappop(frontier)
        if g != g_score[current]:
            continue
        if current == goal:
            path = [current]
            while current in parent:
                current = parent[current]
                path.append(current)
            return list(reversed(path))
        for q in grid.neighbors(current):
            candidate = g + 1
            if candidate < g_score.get(q, 10**12):
                g_score[q] = candidate
                parent[q] = current
                heappush(frontier, (candidate + manhattan(q, goal), candidate, next(serial), q))
    return None


def space_time_astar(
    grid: Grid,
    start: Point,
    goal: Point,
    *,
    constraints: tuple[Constraint, ...] = (),
    reservations: Reservations | None = None,
    horizon: int | None = None,
    deadline: float | None = None,
) -> list[Point] | None:
    if not grid.walkable(start) or not grid.walkable(goal):
        return None
    if grid.distance(start, goal) is None:
        return None
    vertices = {(c.vertex, c.time) for c in constraints if c.vertex is not None}
    edges = {(c.edge, c.time) for c in constraints if c.edge is not None}
    if (start, 0) in vertices or (reservations and not reservations.permits(start, start, 0)):
        return None
    # After the final finite constraint, a simple path needs at most |V|-1 moves.
    # This bound is complete for finite CBS constraints, unlike an arbitrary horizon.
    last = max((c.time for c in constraints), default=0)
    limit = horizon if horizon is not None else last + grid.width * grid.height
    serial = count()
    origin = (start, 0)
    frontier = [(manhattan(start, goal), 0, next(serial), start)]
    seen = {origin}
    parent: dict[tuple[Point, int], tuple[Point, int]] = {}
    while frontier:
        if deadline is not None and perf_counter() >= deadline:
            raise PlanningTimeout
        _, t, _, p = heappop(frontier)
        future_safe = not any(
            (c.vertex == goal or c.edge == (goal, goal)) and c.time > t for c in constraints
        )
        if p == goal and future_safe and (reservations is None or reservations.safe_to_stay(p, t)):
            key = (p, t)
            path = [p]
            while key in parent:
                key = parent[key]
                path.append(key[0])
            return list(reversed(path))
        if t >= limit:
            continue
        for q in [*grid.neighbors(p), p]:
            nt = t + 1
            key = (q, nt)
            if key in seen or (q, nt) in vertices or ((p, q), nt) in edges:
                continue
            if reservations and not reservations.permits(p, q, nt):
                continue
            seen.add(key)
            parent[key] = (p, t)
            heappush(frontier, (nt + manhattan(q, goal), nt, next(serial), q))
    return None
