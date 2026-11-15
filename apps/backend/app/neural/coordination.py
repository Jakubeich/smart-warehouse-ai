"""Choose compatible simultaneous actions from the network's ranked moves."""

from heapq import heappop, heappush
from itertools import count
from typing import NamedTuple

from app.domain.models import Point
from app.scheduling.assignment import INFEASIBLE, hungarian


class QueueTrigger(NamedTuple):
    robots: int
    wait_ticks: int
    fraction_complete: float
    delivery_delay: int


class CoordinationWeights(NamedTuple):
    stalled_ticks: int
    duration: int
    movement: float
    progress: float
    revisit: float
    baseline: float
    delivery_delay: int
    cooldown: int
    fraction_complete: float
    prefer_waiting_robots: bool
    release_pickups: bool
    queue_trigger: QueueTrigger | None = None


def simultaneous_moves(
    origins: dict[str, Point],
    ranked: dict[str, list[tuple[float, Point]]],
) -> dict[str, Point] | None:
    """Maximize summed neural scores without co-location or head-on swaps."""
    if not ranked:
        return origins.copy()
    robots = list(ranked)
    stationary = origins.keys() - ranked.keys()
    occupied = {origins[robot] for robot in stationary}
    cells = sorted({cell for choices in ranked.values() for _, cell in choices} - occupied)
    columns = {cell: index for index, cell in enumerate(cells)}
    owner = {cell: robot for robot, cell in origins.items()}
    row_index = {robot: index for index, robot in enumerate(robots)}
    costs = [[float(INFEASIBLE)] * len(cells) for _ in robots]
    for row, robot in enumerate(robots):
        best = ranked[robot][0][0]
        for score, cell in ranked[robot]:
            if cell in columns:
                costs[row][columns[cell]] = best - score

    def solve(forbidden: frozenset[tuple[int, int]]) -> tuple[float, dict[str, Point]]:
        matrix = [row.copy() for row in costs]
        for row, col in forbidden:
            matrix[row][col] = float(INFEASIBLE)
        pairs = hungarian(matrix)
        total = sum(matrix[row][col] for row, col in pairs)
        return total, {robots[row]: cells[col] for row, col in pairs}

    # Each swap requires at least one of its two assignments to change.
    order = count()
    initial: frozenset[tuple[int, int]] = frozenset()
    cost, moves = solve(initial)
    pending = [(cost, next(order), initial, moves)]
    visited = {initial}
    for _ in range(30):
        if not pending:
            break
        total, _, forbidden, moves = heappop(pending)
        if total >= INFEASIBLE:
            break
        swap = next(
            (
                (robot, other)
                for robot in robots
                if (other := owner.get(moves[robot])) is not None
                and other != robot
                and moves.get(other) == origins[robot]
            ),
            None,
        )
        if swap is None:
            return {**origins, **moves}
        for robot in swap:
            blocked = forbidden | {(row_index[robot], columns[moves[robot]])}
            if blocked not in visited:
                visited.add(blocked)
                cost, alternate = solve(blocked)
                heappush(pending, (cost, next(order), blocked, alternate))
    return None
