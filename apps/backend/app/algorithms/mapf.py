"""MAPF planners with explicit failure, timeout and stay-at-goal semantics."""

from dataclasses import dataclass, field
from heapq import heappop, heappush
from itertools import count
from time import perf_counter

from app.algorithms.pathfinding import (
    Constraint,
    PlanningTimeout,
    Reservations,
    astar,
    space_time_astar,
)
from app.domain.grid import Grid
from app.domain.models import Point


@dataclass(frozen=True)
class Conflict:
    a: str
    b: str
    time: int
    vertex: Point | None = None
    a_edge: tuple[Point, Point] | None = None
    b_edge: tuple[Point, Point] | None = None


@dataclass
class PlanResult:
    status: str
    paths: dict[str, list[Point]] = field(default_factory=dict)
    expanded: int = 0
    conflicts: int = 0
    elapsed_ms: float = 0
    optimal: bool = False
    reason: str = ""
    first_conflict: Conflict | None = None

    @property
    def cost(self) -> int:
        return sum(len(p) - 1 for p in self.paths.values())


def at(path: list[Point], time: int) -> Point:
    return path[min(time, len(path) - 1)]


def first_conflict(paths: dict[str, list[Point]]) -> Conflict | None:
    ids = sorted(paths)
    for t in range(max((len(p) for p in paths.values()), default=0)):
        for i, a in enumerate(ids):
            for b in ids[i + 1 :]:
                pa, pb = at(paths[a], t), at(paths[b], t)
                if pa == pb:
                    return Conflict(a, b, t, vertex=pa)
                if t and at(paths[a], t - 1) == pb and at(paths[b], t - 1) == pa:
                    return Conflict(a, b, t, a_edge=(pb, pa), b_edge=(pa, pb))
    return None


def validate_problem(grid: Grid, starts: dict[str, Point], goals: dict[str, Point]) -> None:
    if not starts or starts.keys() != goals.keys():
        raise ValueError("Starts and goals must have the same nonempty robot IDs")
    if len(set(starts.values())) != len(starts) or len(set(goals.values())) != len(goals):
        raise ValueError("Initial and goal positions must each be unique (stay-at-goal)")
    if not all(grid.walkable(p) for p in [*starts.values(), *goals.values()]):
        raise ValueError("All endpoints must be traversable")


def plan(
    grid: Grid,
    starts: dict[str, Point],
    goals: dict[str, Point],
    method: str,
    *,
    horizon: int = 128,
    max_nodes: int = 2000,
    timeout: float = 2,
    order: list[str] | None = None,
) -> PlanResult:
    began = perf_counter()
    deadline = began + timeout
    validate_problem(grid, starts, goals)
    try:
        if method == "cbs":
            result = cbs(grid, starts, goals, max_nodes=max_nodes, deadline=deadline)
        elif method == "astar":
            paths: dict[str, list[Point]] = {}
            for rid in sorted(starts):
                if perf_counter() >= deadline:
                    raise PlanningTimeout
                path = astar(grid, starts[rid], goals[rid])
                if path is None:
                    return PlanResult(
                        "UNSOLVABLE",
                        reason="Disconnected endpoint",
                        elapsed_ms=(perf_counter() - began) * 1000,
                    )
                paths[rid] = path
            conflict = first_conflict(paths)
            result = PlanResult(
                "CONFLICT" if conflict else "SUCCESS",
                paths,
                conflicts=int(conflict is not None),
                first_conflict=conflict,
                reason="Independent A* routes conflict" if conflict else "",
            )
        elif method in {"prioritized", "adaptive"}:
            paths = {}
            reservations = Reservations()
            result = PlanResult("SUCCESS")
            for rid in order or sorted(starts):
                path = space_time_astar(
                    grid,
                    starts[rid],
                    goals[rid],
                    reservations=reservations,
                    horizon=horizon,
                    deadline=deadline,
                )
                if path is None:
                    result = PlanResult(
                        "NO_PLAN", reason="Priority order or horizon prevents a plan"
                    )
                    break
                paths[rid] = path
                reservations.reserve(path)
            if result.status == "SUCCESS":
                result.paths = paths
        else:
            raise ValueError(f"Unknown planner: {method}")
    except PlanningTimeout:
        result = PlanResult("TIMEOUT", reason="Planning time limit exhausted")
    result.elapsed_ms = (perf_counter() - began) * 1000
    return result


def cbs(
    grid: Grid,
    starts: dict[str, Point],
    goals: dict[str, Point],
    *,
    max_nodes: int,
    deadline: float,
) -> PlanResult:
    ids = sorted(starts)
    constraints: dict[str, tuple[Constraint, ...]] = {rid: () for rid in ids}
    paths: dict[str, list[Point]] = {}
    for rid in ids:
        path = space_time_astar(grid, starts[rid], goals[rid], deadline=deadline)
        if path is None:
            return PlanResult("UNSOLVABLE", reason="Disconnected endpoint")
        paths[rid] = path
    serial = count()
    queue = [(sum(len(p) - 1 for p in paths.values()), next(serial), constraints, paths)]
    expanded = 0
    conflicts = 0
    seen: set[frozenset[tuple[str, Constraint]]] = {frozenset()}
    while queue:
        if expanded >= max_nodes or perf_counter() >= deadline:
            return PlanResult(
                "TIMEOUT",
                expanded=expanded,
                conflicts=conflicts,
                reason="CBS resource limit exhausted; feasibility is unknown",
            )
        _, _, constraints, paths = heappop(queue)
        expanded += 1
        conflict = first_conflict(paths)
        if conflict is None:
            # No horizon pruning. Each low-level search is complete and shortest.
            return PlanResult("SUCCESS", paths, expanded, conflicts, optimal=True)
        conflicts += 1
        for rid, edge in [(conflict.a, conflict.a_edge), (conflict.b, conflict.b_edge)]:
            constraint = Constraint(conflict.time, conflict.vertex, edge)
            child_constraints = dict(constraints)
            child_constraints[rid] = (*constraints[rid], constraint)
            key = frozenset((r, c) for r, cs in child_constraints.items() for c in cs)
            if key in seen:
                continue
            seen.add(key)
            try:
                path = space_time_astar(
                    grid,
                    starts[rid],
                    goals[rid],
                    constraints=child_constraints[rid],
                    deadline=deadline,
                )
            except PlanningTimeout:
                return PlanResult(
                    "TIMEOUT",
                    expanded=expanded,
                    conflicts=conflicts,
                    reason="CBS low-level time limit exhausted; feasibility is unknown",
                )
            if path is None:
                continue
            child_paths = dict(paths)
            child_paths[rid] = path
            heappush(
                queue,
                (
                    sum(len(p) - 1 for p in child_paths.values()),
                    next(serial),
                    child_constraints,
                    child_paths,
                ),
            )
    return PlanResult(
        "UNSOLVABLE", expanded=expanded, conflicts=conflicts, reason="Exhausted conflict tree"
    )
