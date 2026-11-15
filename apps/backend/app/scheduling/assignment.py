"""Task assignment is independent of MAPF planning."""

from collections.abc import Callable

from app.domain.grid import Grid
from app.domain.models import AlgorithmConfig, Robot, TransportTask

INFEASIBLE = 10**9


def energy_needed(robot: Robot, task: TransportTask, grid: Grid, config: AlgorithmConfig) -> float:
    first = grid.distance(robot.position, task.pickup)
    delivery = grid.distance(task.pickup, task.dropoff)
    if first is None or delivery is None:
        return float("inf")
    # Conservative return to the robot's own charger when available.
    home = robot.home
    back = grid.distance(task.dropoff, home) if home is not None and home in grid.chargers else None
    if back is None:
        back = min(
            (d for point in grid.chargers if (d := grid.distance(task.dropoff, point)) is not None),
            default=None,
        )
    if back is None:
        return float("inf")
    return (
        (first + delivery + back) * config.move_energy
        + (task.load_duration + task.unload_duration) * config.handling_energy
        + config.critical_threshold
    )


def feasible(robot: Robot, task: TransportTask, grid: Grid, config: AlgorithmConfig) -> bool:
    return robot.capacity >= task.payload_weight and robot.battery >= energy_needed(
        robot, task, grid, config
    )


def hungarian(costs: list[list[float]]) -> list[tuple[int, int]]:
    """Rectangular minimum-cost matching, O(min(n,m)^2 max(n,m))."""
    if not costs or not costs[0]:
        return []
    n, m = len(costs), len(costs[0])
    if any(len(row) != m for row in costs):
        raise ValueError("Ragged cost matrix")
    transpose = n > m
    a = [list(row) for row in zip(*costs)] if transpose else costs
    n, m = len(a), len(a[0])
    u, v = [0.0] * (n + 1), [0.0] * (m + 1)
    p, way = [0] * (m + 1), [0] * (m + 1)
    for i in range(1, n + 1):
        p[0] = i
        j0 = 0
        minimum, used = [float("inf")] * (m + 1), [False] * (m + 1)
        while True:
            used[j0] = True
            i0, delta, j1 = p[j0], float("inf"), 0
            for j in range(1, m + 1):
                if not used[j]:
                    cur = a[i0 - 1][j - 1] - u[i0] - v[j]
                    if cur < minimum[j]:
                        minimum[j], way[j] = cur, j0
                    if minimum[j] < delta:
                        delta, j1 = minimum[j], j
            for j in range(m + 1):
                if used[j]:
                    u[p[j]] += delta
                    v[j] -= delta
                else:
                    minimum[j] -= delta
            j0 = j1
            if p[j0] == 0:
                break
        while True:
            j1 = way[j0]
            p[j0] = p[j1]
            j0 = j1
            if j0 == 0:
                break
    pairs = [(p[j] - 1, j - 1) for j in range(1, m + 1) if p[j]]
    return [(j, i) for i, j in pairs] if transpose else pairs


def assign(
    robots: list[Robot],
    tasks: list[TransportTask],
    grid: Grid,
    config: AlgorithmConfig,
    *,
    estimate: Callable[[Robot, TransportTask], float] | None = None,
) -> list[tuple[Robot, TransportTask]]:
    if config.scheduler == "learned" and estimate is None:
        raise ValueError(
            "ML přiřazování vyžaduje natrénovaný model. Nejdříve jej vytvořte ve Strojovém učení."
        )
    available = sorted(robots, key=lambda r: r.id)
    pending = sorted(
        tasks,
        key=lambda t: ((-t.priority if config.scheduler != "nearest" else 0), t.created_tick, t.id),
    )
    if config.scheduler == "hungarian":
        costs = [
            [
                float(grid.distance(r.position, t.pickup) or 0)
                if feasible(r, t, grid, config)
                else float(INFEASIBLE)
                for t in pending
            ]
            for r in available
        ]
        return [(available[i], pending[j]) for i, j in hungarian(costs) if costs[i][j] < INFEASIBLE]
    pairs: list[tuple[Robot, TransportTask]] = []
    for task in pending:
        candidates = [r for r in available if feasible(r, task, grid, config)]
        if not candidates:
            continue
        robot = min(
            candidates,
            key=lambda r: (
                estimate(r, task)
                if config.scheduler == "learned" and estimate is not None
                else (grid.distance(r.position, task.pickup) or 0)
                + (
                    (1 - r.battery / r.battery_capacity) * 5
                    if config.scheduler == "priority"
                    else 0
                ),
                r.id,
            ),
        )
        pairs.append((robot, task))
        available.remove(robot)
    return pairs
