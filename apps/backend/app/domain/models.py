"""Versioned simulation domain. Coordinates are integral, top-left origin."""

from enum import StrEnum
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

Point = tuple[int, int]
Finite = Annotated[float, Field(allow_inf_nan=False)]


class Model(BaseModel):
    model_config = ConfigDict(extra="forbid", validate_assignment=True)


class CellType(StrEnum):
    FLOOR = "FLOOR"
    WALL = "WALL"
    SHELF = "SHELF"
    PICKUP = "PICKUP"
    DROPOFF = "DROPOFF"
    CHARGER = "CHARGER"
    OBSTACLE = "OBSTACLE"


class Cell(Model):
    x: int
    y: int
    type: CellType


class Warehouse(Model):
    schema_version: Literal[1] = 1
    id: str = Field(min_length=1, max_length=100)
    name: str = Field(min_length=1, max_length=120)
    width: int = Field(ge=4, le=64)
    height: int = Field(ge=4, le=64)
    cell_size: Finite = Field(default=1.0, gt=0, le=10)
    cells: list[Cell] = Field(default_factory=list, max_length=4096)
    metadata: dict[str, str] = Field(default_factory=dict)

    @model_validator(mode="after")
    def validate_cells(self) -> "Warehouse":
        seen: set[Point] = set()
        for c in self.cells:
            if not (0 <= c.x < self.width and 0 <= c.y < self.height):
                raise ValueError("Cell outside warehouse")
            if (c.x, c.y) in seen:
                raise ValueError("Duplicate cell coordinates")
            seen.add((c.x, c.y))
        return self


class RobotStatus(StrEnum):
    IDLE = "IDLE"
    ASSIGNED = "ASSIGNED"
    MOVING_TO_PICKUP = "MOVING_TO_PICKUP"
    LOADING = "LOADING"
    MOVING_TO_DROPOFF = "MOVING_TO_DROPOFF"
    UNLOADING = "UNLOADING"
    WAITING = "WAITING"
    CHARGING = "CHARGING"
    BLOCKED = "BLOCKED"
    ERROR = "ERROR"


class Robot(Model):
    id: str = Field(min_length=1, max_length=80)
    name: str = Field(min_length=1, max_length=100)
    position: Point
    home: Point | None = None
    orientation: int = 0
    status: RobotStatus = RobotStatus.IDLE
    task_id: str | None = None
    path: list[Point] = Field(default_factory=list)
    path_index: int = 0
    battery_capacity: Finite = Field(default=100, gt=0, le=10000)
    battery: Finite = Field(default=100, ge=0, le=10000)
    capacity: Finite = Field(default=50, gt=0, le=10000)
    load: Finite = 0
    completed_tasks: int = 0
    distance: int = 0
    waiting: int = 0
    busy_ticks: int = 0
    mode: Literal["IDLE", "PICKUP", "DROPOFF", "RETURN", "CHARGE", "OFFLINE"] = "IDLE"
    service_remaining: int = 0
    goal: Point | None = None

    @model_validator(mode="after")
    def battery_range(self) -> "Robot":
        if self.battery > self.battery_capacity:
            raise ValueError("Battery exceeds capacity")
        return self


class TaskStatus(StrEnum):
    PENDING = "PENDING"
    ASSIGNED = "ASSIGNED"
    IN_PROGRESS = "IN_PROGRESS"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"
    CANCELLED = "CANCELLED"


class TransportTask(Model):
    id: str = Field(min_length=1, max_length=80)
    pickup: Point
    dropoff: Point
    priority: int = Field(default=1, ge=1, le=10)
    created_tick: int = Field(default=0, ge=0)
    assigned_robot: str | None = None
    status: TaskStatus = TaskStatus.PENDING
    load_duration: int = Field(default=2, ge=1, le=100)
    unload_duration: int = Field(default=2, ge=1, le=100)
    assigned_tick: int | None = None
    pickup_tick: int | None = None
    completed_tick: int | None = None
    deadline: int | None = Field(default=None, ge=0)
    payload_weight: Finite = Field(default=10, gt=0, le=10000)


class AlgorithmConfig(Model):
    control: Literal["classical", "neural"] = "classical"
    neural_model_id: str | None = None
    planner: Literal["astar", "prioritized", "cbs", "adaptive"] = "adaptive"
    scheduler: Literal["nearest", "priority", "hungarian", "learned"] = "priority"
    ml_model_id: str | None = None
    horizon: int = Field(default=128, ge=8, le=512)
    max_nodes: int = Field(default=2000, ge=1, le=20000)
    timeout_seconds: Finite = Field(default=2.0, ge=0.01, le=10)
    move_energy: Finite = Field(default=0.4, ge=0, le=10)
    wait_energy: Finite = Field(default=0, ge=0, le=1)
    handling_energy: Finite = Field(default=0.1, ge=0, le=10)
    charging_rate: Finite = Field(default=4, gt=0, le=100)
    critical_threshold: Finite = Field(default=15, ge=0, le=100)
    tick_seconds: Finite = Field(default=1, gt=0, le=60)


class Scenario(Model):
    schema_version: Literal[1] = 1
    id: str = Field(min_length=1, max_length=100)
    name: str = Field(min_length=1, max_length=120)
    warehouse: Warehouse
    robots: list[Robot] = Field(min_length=1, max_length=32)
    tasks: list[TransportTask] = Field(default_factory=list, max_length=500)
    seed: int = Field(default=42, ge=0, le=2**32 - 1)
    config: AlgorithmConfig = Field(default_factory=AlgorithmConfig)

    @model_validator(mode="after")
    def validate_scene(self) -> "Scenario":
        from app.domain.grid import Grid

        grid = Grid(self.warehouse)
        for items in [[r.id for r in self.robots], [t.id for t in self.tasks]]:
            ids = items
            if len(ids) != len(set(ids)):
                raise ValueError("Entity IDs must be unique within a collection")
        positions = [r.position for r in self.robots]
        if len(positions) != len(set(positions)):
            raise ValueError("Robots cannot share a start cell")
        homes = [r.home or r.position for r in self.robots]
        if len(homes) != len(set(homes)):
            raise ValueError("Robots must have distinct home cells")
        for robot in self.robots:
            if not grid.walkable(robot.position) or not grid.walkable(robot.home or robot.position):
                raise ValueError("Robot start/home must be traversable")
        for task in self.tasks:
            if grid.kind(task.pickup) != CellType.PICKUP:
                raise ValueError("Task pickup must be a PICKUP station")
            if grid.kind(task.dropoff) != CellType.DROPOFF:
                raise ValueError("Task dropoff must be a DROPOFF station")
            if grid.distance(task.pickup, task.dropoff) is None:
                raise ValueError("Task stations are disconnected")
            if not any(grid.distance(r.position, task.pickup) is not None for r in self.robots):
                raise ValueError("No robot can reach task pickup")
        return self


class Event(Model):
    tick: int
    type: str
    message: str
    entity_id: str | None = None


class Metrics(Model):
    makespan: int = 0
    sum_of_costs: int = 0
    completed_tasks: int = 0
    task_completion_rate: float = 0
    average_task_completion_time: float = 0
    total_distance: float = 0
    total_waiting: int = 0
    planning_time_ms: float = 0
    replans: int = 0
    planning_conflicts: int = 0
    executed_collisions: int = 0
    success: bool = False
    throughput: float = 0


class AssignmentCandidate(Model):
    robot_id: str
    predicted_ticks: float
    geometric_ticks: float
    route_occupied: int = 0
    route_opposing_edges: int = 0


class AssignmentDecision(Model):
    task_id: str
    robot_id: str
    tick: int
    model_id: str
    candidates: list[AssignmentCandidate]


class NeuralDecision(Model):
    robot_id: str
    action: Literal["task", "charge", "park", "idle", "move", "wait"]
    target: Point
    task_id: str | None = None
    score: float


class TrainingAttempt(Model):
    status: Literal["COMPLETED", "FAILED"]
    ticks: int
    completed_tasks: int
    model_updates: int
    error: str | None = None


class TrainingLoop(Model):
    active: bool = True
    attempt: int = 1
    finished_attempts: int = 0
    best_completed_tasks: int = 0
    last_result: TrainingAttempt | None = None


class SimulationState(Model):
    schema_version: Literal[1] = 1
    id: str
    scenario_id: str
    name: str
    tick: int = 0
    status: Literal["READY", "RUNNING", "PAUSED", "COMPLETED", "FAILED", "STOPPED"] = "READY"
    config: AlgorithmConfig
    robots: list[Robot]
    tasks: list[TransportTask]
    warehouse: Warehouse
    obstacles: list[Point] = Field(default_factory=list)
    events: list[Event] = Field(default_factory=list)
    metrics: Metrics = Field(default_factory=Metrics)
    seed: int
    sequence: int = 0
    speed: float = 1
    reservations: list[dict[str, str | int]] = Field(default_factory=list)
    conflicts: list[dict[str, object]] = Field(default_factory=list)
    heatmap: dict[str, int] = Field(default_factory=dict)
    history: list[dict[str, float | int]] = Field(default_factory=list)
    error: str | None = None
    planner_status: str | None = None
    neural_decisions: list[NeuralDecision] = Field(default_factory=list)
    neural_rejections: int = 0
    neural_last_model_id: str | None = None
    neural_updates: int = 0
    neural_learned_samples: int = 0
    training_loop: TrainingLoop | None = None
    assignment_decisions: list[AssignmentDecision] = Field(default_factory=list)
