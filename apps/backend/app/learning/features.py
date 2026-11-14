"""Dispatch-time features: geometric routes and currently published plans, never outcomes."""

from app.domain.grid import Grid
from app.domain.models import Robot, SimulationState, TransportTask

FEATURE_VERSION = 2
ROUTE_HORIZON = 64
LEGACY_FEATURE_NAMES = [
    "pickup_distance",
    "delivery_distance",
    "handling_ticks",
    "fleet_size",
    "active_robots",
    "pending_tasks",
    "blocked_ratio",
    "battery_ratio",
    "payload_ratio",
    "robots_near_pickup",
    "robots_near_dropoff",
    "map_width",
    "map_height",
    "local_degree",
    "planner_cbs",
    "planner_adaptive",
]


ROUTE_FEATURE_NAMES = [
    "pickup_route_occupied",
    "delivery_route_occupied",
    "route_stationary_blockers",
    "route_reserved_overlap",
    "route_vertex_conflicts",
    "route_head_on_conflicts",
    "route_opposing_edges",
    "route_same_direction_edges",
    "route_narrow_cells",
    "route_narrow_occupied",
    "route_service_ticks",
]
FEATURE_NAMES = LEGACY_FEATURE_NAMES + ROUTE_FEATURE_NAMES


def route_features(
    state: SimulationState, robot: Robot, task: TransportTask, grid: Grid
) -> list[float]:
    first = grid.shortest_path(robot.position, task.pickup)
    delivery = grid.shortest_path(task.pickup, task.dropoff)
    if not first or not delivery:
        raise ValueError("Nelze odhadnout čas nedosažitelného úkolu.")
    # Nominal arrivals include known handling time, but do not invoke the planner.
    nominal = (
        first
        + [task.pickup] * task.load_duration
        + delivery[1:]
        + [task.dropoff] * task.unload_duration
    )[: ROUTE_HORIZON + 1]
    route = set(first + delivery)
    narrow = {p for p in route if len(grid.neighbors(p)) <= 2}
    first_cells, delivery_cells = set(first), set(delivery)
    edges = {(a, b) for a, b in zip(nominal, nominal[1:]) if a != b}
    occupied_first = occupied_delivery = stationary = overlap = vertices = head_on = 0
    opposing = same = narrow_occupied = service = 0
    for other in state.robots:
        if other.id == robot.id:
            continue
        occupied_first += other.position in first_cells
        occupied_delivery += other.position in delivery_cells
        narrow_occupied += other.position in narrow
        if other.position in route:
            stationary += other.mode in {"IDLE", "OFFLINE", "CHARGE"} or other.service_remaining > 0
            service += other.service_remaining
        # Only the existing plan is observed. Beyond it, use its terminal occupancy,
        # as in stay-at-goal reservations; later replanning remains unknown.
        remaining = other.path[other.path_index : other.path_index + ROUTE_HORIZON + 1]
        if not remaining or remaining[0] != other.position:
            remaining = [other.position]
        overlap += len(route.intersection(remaining))
        other_edges = {(a, b) for a, b in zip(remaining, remaining[1:]) if a != b}
        opposing += sum((b, a) in other_edges for a, b in edges)
        same += len(edges.intersection(other_edges))
        for t in range(1, len(nominal)):
            current = remaining[min(t, len(remaining) - 1)]
            previous = remaining[min(t - 1, len(remaining) - 1)]
            vertices += nominal[t] == current
            head_on += (
                nominal[t] != nominal[t - 1]
                and nominal[t] == previous
                and nominal[t - 1] == current
            )
    return [
        float(x)
        for x in [
            occupied_first,
            occupied_delivery,
            stationary,
            overlap,
            vertices,
            head_on,
            opposing,
            same,
            len(narrow),
            narrow_occupied,
            service,
        ]
    ]


def features(state: SimulationState, robot: Robot, task: TransportTask, grid: Grid) -> list[float]:
    first, delivery = (
        grid.distance(robot.position, task.pickup),
        grid.distance(task.pickup, task.dropoff),
    )
    if first is None or delivery is None:
        raise ValueError("Nelze odhadnout čas nedosažitelného úkolu.")
    others = [r for r in state.robots if r.id != robot.id]

    def nearby(point: tuple[int, int]) -> int:
        return sum(
            abs(r.position[0] - point[0]) + abs(r.position[1] - point[1]) <= 3 for r in others
        )

    return [
        float(first),
        float(delivery),
        float(task.load_duration + task.unload_duration),
        float(len(state.robots)),
        float(sum(r.mode not in {"IDLE", "OFFLINE"} for r in others)),
        float(sum(t.status == "PENDING" for t in state.tasks)),
        len(grid.blocked) / (grid.width * grid.height),
        robot.battery / robot.battery_capacity,
        task.payload_weight / robot.capacity,
        float(nearby(task.pickup)),
        float(nearby(task.dropoff)),
        float(grid.width),
        float(grid.height),
        float(len(grid.neighbors(robot.position))),
        float(state.config.planner == "cbs"),
        float(state.config.planner == "adaptive"),
    ] + route_features(state, robot, task, grid)


def geometric_eta(values: list[float]) -> float:
    return values[0] + values[1] + values[2]
