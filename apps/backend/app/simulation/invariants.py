from app.domain.grid import Grid, manhattan
from app.domain.models import Point, RobotStatus, SimulationState, TaskStatus


class InvariantError(ValueError):
    pass


TRANSITIONS: dict[RobotStatus, set[RobotStatus]] = {
    RobotStatus.IDLE: {RobotStatus.ASSIGNED, RobotStatus.CHARGING, RobotStatus.WAITING},
    RobotStatus.ASSIGNED: {RobotStatus.MOVING_TO_PICKUP, RobotStatus.LOADING},
    RobotStatus.MOVING_TO_PICKUP: {RobotStatus.LOADING, RobotStatus.WAITING},
    RobotStatus.LOADING: {RobotStatus.MOVING_TO_DROPOFF},
    RobotStatus.MOVING_TO_DROPOFF: {RobotStatus.UNLOADING, RobotStatus.WAITING},
    RobotStatus.UNLOADING: {RobotStatus.IDLE, RobotStatus.WAITING},
    RobotStatus.WAITING: {
        RobotStatus.MOVING_TO_PICKUP,
        RobotStatus.MOVING_TO_DROPOFF,
        RobotStatus.LOADING,
        RobotStatus.UNLOADING,
        RobotStatus.CHARGING,
        RobotStatus.IDLE,
        RobotStatus.ASSIGNED,
    },
    RobotStatus.CHARGING: {RobotStatus.IDLE, RobotStatus.WAITING},
    RobotStatus.BLOCKED: {
        RobotStatus.WAITING,
        RobotStatus.IDLE,
        RobotStatus.MOVING_TO_PICKUP,
        RobotStatus.MOVING_TO_DROPOFF,
    },
    RobotStatus.ERROR: {RobotStatus.IDLE},
}


def validate_transition(grid: Grid, old: dict[str, Point], new: dict[str, Point]) -> None:
    if old.keys() != new.keys():
        raise InvariantError("Transition changed fleet membership")
    if len(set(new.values())) != len(new):
        raise InvariantError("Vertex collision rejected")
    previous_occupants = {position: rid for rid, position in old.items()}
    for rid, target in new.items():
        if not grid.walkable(target) or manhattan(old[rid], target) > 1:
            raise InvariantError("Invalid robot movement rejected")
        other = previous_occupants.get(target)
        if other is not None and other != rid and new[other] == old[rid]:
            raise InvariantError("Edge-swap collision rejected")


def validate_state(state: SimulationState, grid: Grid | None = None) -> None:
    grid = grid or Grid(state.warehouse, set(state.obstacles))
    pos = {r.id: r.position for r in state.robots}
    validate_transition(grid, pos, pos)
    for r in state.robots:
        if not 0 <= r.battery <= r.battery_capacity:
            raise InvariantError("Invalid battery level")
    for task in state.tasks:
        if task.status == TaskStatus.COMPLETED:
            if (
                task.assigned_tick is None
                or task.pickup_tick is None
                or task.completed_tick is None
                or task.assigned_robot is None
                or not task.created_tick
                <= task.assigned_tick
                <= task.pickup_tick
                <= task.completed_tick
            ):
                raise InvariantError("Invalid completed task history")
