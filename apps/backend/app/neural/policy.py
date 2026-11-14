"""Learned candidate ranking for dispatch, charging and joint grid movement."""

import hashlib
import json
from collections import deque
from collections.abc import Sequence
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Any, Literal, Protocol

import numpy as np
from numpy.typing import NDArray

from app.domain.grid import Grid, manhattan
from app.domain.models import CellType, Point, Robot, SimulationState, TransportTask
from app.scheduling.assignment import energy_needed

Mode = Literal["task", "charge", "park", "idle", "move"]
KINDS = ("task", "charge", "park", "idle", "move")
# Dispatch and motion share the network. Feature slots beyond the common
# context are specific to their decision type.
FEATURE_VERSION = 1
FEATURE_COUNT = 44
MODEL_PATH = Path(__file__).with_name("fleet-policy.json")
REPORT_PATH = Path(__file__).with_name("fleet-evaluation.json")


@dataclass(frozen=True)
class Action:
    kind: Mode
    target: Point
    values: tuple[float, ...]
    task: TransportTask | None = None
    distance_gain: float = 0.0
    recent_visits: float = 0.0


class Policy(Protocol):
    id: str

    def scores(self, actions: Sequence[Action]) -> list[float]: ...


def weight_id(layers: list[dict[str, Any]]) -> str:
    digest = hashlib.sha256(json.dumps(layers, separators=(",", ":")).encode()).hexdigest()
    return f"nn-{digest[:12]}"


class NeuralPolicy:
    def __init__(self, artifact: dict[str, Any]):
        if artifact["feature_version"] != FEATURE_VERSION:
            raise ValueError("Model neuronového řízení používá jinou verzi vstupů.")
        payload = artifact["layers"]
        self.feature_version = FEATURE_VERSION
        if artifact["id"] != weight_id(payload):
            raise ValueError("Váhy neuronového řízení neodpovídají identifikátoru modelu.")
        self.id = artifact["id"]
        self.training = artifact["training"]
        self.layers: list[tuple[NDArray[np.float64], NDArray[np.float64]]] = []
        width = FEATURE_COUNT
        for layer in payload:
            weights = np.asarray(layer["weights"], dtype=np.float64)
            bias = np.asarray(layer["bias"], dtype=np.float64)
            if (
                weights.ndim != 2
                or weights.shape[0] != width
                or bias.shape != (weights.shape[1],)
                or not np.isfinite(weights).all()
                or not np.isfinite(bias).all()
            ):
                raise ValueError("Neplatné váhy neuronového řízení.")
            self.layers.append((weights, bias))
            width = weights.shape[1]
        if len(self.layers) < 2 or width != 1:
            raise ValueError("Neplatná architektura neuronového řízení.")

    def scores(self, actions: Sequence[Action]) -> list[float]:
        values = np.asarray([a.values for a in actions], dtype=np.float64)
        for weights, bias in self.layers[:-1]:
            values = np.maximum(values @ weights + bias, 0)
        weights, bias = self.layers[-1]
        return (values @ weights + bias).ravel().tolist()


@lru_cache(maxsize=1)
def load_policy() -> NeuralPolicy:
    try:
        return NeuralPolicy(json.loads(MODEL_PATH.read_text()))
    except (OSError, ValueError, KeyError, TypeError) as exc:
        raise ValueError("Model neuronového řízení se nepodařilo načíst.") from exc


def overview() -> dict[str, Any]:
    policy = load_policy()
    evaluation = json.loads(REPORT_PATH.read_text()) if REPORT_PATH.exists() else None
    return {
        "id": policy.id,
        "architecture": [FEATURE_COUNT, *(int(bias.size) for _, bias in policy.layers)],
        "training": {key: policy.training[key] for key in ("maps", "rows", "epochs", "status")},
        "evaluation": evaluation if evaluation and evaluation["model"] == policy.id else None,
    }


def context(kind: Mode, robot: Robot, state: SimulationState) -> tuple[float, ...]:
    return (
        *(float(kind == name) for name in KINDS),
        robot.battery / robot.battery_capacity,
        min(robot.battery / 200, 2),
        robot.load / robot.capacity,
        len(state.robots) / 32,
    )


def action_features(
    kind: Mode, robot: Robot, state: SimulationState, variables: tuple[float, ...]
) -> tuple[float, ...]:
    values = context(kind, robot, state) + variables
    return values + (0.0,) * (FEATURE_COUNT - len(values))


def dispatch_actions(
    state: SimulationState,
    grid: Grid,
    robot: Robot,
    pending: Sequence[TransportTask],
    stations: set[Point],
    goals: set[Point],
    occupied: set[Point],
) -> list[Action]:
    actions = []
    eligible = []
    chargers = [p for p, kind in grid.cells.items() if kind == CellType.CHARGER]
    for task in pending:
        if {task.pickup, task.dropoff} & (stations | goals) or task.pickup in occupied:
            continue
        if task.payload_weight > robot.capacity:
            continue
        cost = energy_needed(robot, task, grid, state.config)
        if cost <= robot.battery:
            eligible.append((task, cost))
    for task, cost in eligible:
        pickup = grid.distance(robot.position, task.pickup)
        delivery = grid.distance(task.pickup, task.dropoff)
        assert pickup is not None and delivery is not None
        actions.append(
            Action(
                "task",
                task.pickup,
                action_features(
                    "task",
                    robot,
                    state,
                    (
                        float(bool(eligible)),
                        float(bool(pending)),
                        pickup / 32,
                        delivery / 32,
                        task.priority / 10,
                        min((state.tick - task.created_tick) / 200, 2),
                        (robot.battery - cost) / robot.battery_capacity,
                        task.payload_weight / robot.capacity,
                        (task.load_duration + task.unload_duration) / 20,
                        min(pickup + delivery, 160) / 80,
                        float(robot.position == robot.home),
                    ),
                ),
                task,
            )
        )

    for point in dict.fromkeys([*chargers, robot.home]):
        if point is None or point in goals or point in stations or point in occupied:
            continue
        distance = grid.distance(robot.position, point)
        if distance is None or distance * state.config.move_energy > robot.battery:
            continue
        is_charger = grid.kind(point) == CellType.CHARGER
        if is_charger and robot.battery < robot.battery_capacity:
            kind: Mode = "charge"
        elif point == robot.home and distance:
            kind = "park"
        else:
            continue
        actions.append(
            Action(
                kind,
                point,
                action_features(
                    kind,
                    robot,
                    state,
                    (
                        float(bool(eligible)),
                        float(bool(pending)),
                        distance / 32,
                        0,
                        0,
                        0,
                        0,
                        0,
                        0,
                        0,
                        float(robot.position == robot.home),
                        float(point == robot.home),
                        float(robot.battery < state.config.critical_threshold),
                        float(is_charger),
                        float(distance == 0),
                    ),
                ),
            )
        )
    actions.append(
        Action(
            "idle",
            robot.position,
            action_features(
                "idle",
                robot,
                state,
                (
                    float(bool(eligible)),
                    float(bool(pending)),
                    0,
                    0,
                    0,
                    0,
                    0,
                    0,
                    0,
                    0,
                    float(robot.position == robot.home),
                    0,
                    float(robot.battery < state.config.critical_threshold),
                ),
            ),
        )
    )
    return actions


def motion_actions(
    state: SimulationState,
    grid: Grid,
    open_grid: Grid,
    robot: Robot,
    occupants: dict[Point, Robot],
    visits: deque[Point],
) -> list[Action]:
    if (
        robot.mode == "OFFLINE"
        or robot.goal is None
        or robot.goal == robot.position
        or robot.service_remaining
    ):
        return []
    goal = robot.goal
    origin = robot.position
    current = grid.distance(origin, goal)
    dynamic = open_grid.distance(origin, goal)
    actions = []
    points = [origin, *open_grid.neighbors(origin)]
    for point in points:
        if point != origin and robot.battery < state.config.move_energy:
            continue
        distance = grid.distance(point, goal)
        dynamic_next = open_grid.distance(point, goal)
        dx, dy = point[0] - origin[0], point[1] - origin[1]
        towards = (goal[0] - origin[0], goal[1] - origin[1])
        neighbor = occupants.get(point) if point != origin else None
        opposing = following = 0
        # Local view in the direction of travel includes the other robot's current intent.
        if dx or dy:
            for n in range(1, 7):
                seen = (origin[0] + n * dx, origin[1] + n * dy)
                if not grid.walkable(seen):
                    break
                other = occupants.get(seen)
                if other is not None and other.goal is not None:
                    desired = (other.goal[0] - seen[0]) * dx + (other.goal[1] - seen[1]) * dy
                    opposing += desired < 0
                    following += desired > 0
        adjacent = grid.neighbors(point)
        distance_gain = float(
            dynamic - dynamic_next if dynamic is not None and dynamic_next is not None else 0
        )
        recent_visits = visits.count(point) / 12
        values = (
            float(point == origin),
            float(point == goal),
            (distance if distance is not None else 256) / 64,
            (dynamic_next if dynamic_next is not None else 256) / 64,
            float((current - distance) if current is not None and distance is not None else 0),
            distance_gain,
            float(dynamic_next is None),
            float(distance is None),
            float(dx),
            float(dy),
            float(towards[0] * dx + towards[1] * dy) / 32,
            manhattan(point, goal) / 64,
            len(adjacent) / 4,
            len(grid.neighbors(origin)) / 4,
            float(neighbor is not None),
            float(neighbor is not None and neighbor.goal == origin),
            opposing / 3,
            following / 3,
            sum(q in occupants for q in adjacent) / 4,
            recent_visits,
            float(len(visits) > 1 and point == visits[-2]),
            float(robot.mode == "PICKUP"),
            float(robot.mode == "DROPOFF"),
            float(robot.mode == "RETURN"),
            float(origin[0] < grid.width // 2),
            float(goal[0] < grid.width // 2),
            abs(origin[0] - grid.width // 2) / 32,
            robot.service_remaining / 20,
            float(dynamic == current),
            float(dynamic is None),
            min(robot.waiting, 100) / 100,
        )
        actions.append(
            Action(
                "move",
                point,
                action_features("move", robot, state, values),
                distance_gain=distance_gain,
                recent_visits=recent_visits,
            )
        )
    return actions


def resolve_moves(
    origins: dict[str, Point],
    ranked: dict[str, list[tuple[float, Point]]],
) -> tuple[dict[str, Point], int]:
    """Reject colliding proposals and try the next neural choice, with wait as a legal action."""
    candidates = {rid: list(options) for rid, options in ranked.items()}
    chosen = {
        rid: candidates[rid][0][1] if rid in candidates else point for rid, point in origins.items()
    }
    rejected = 0
    while True:
        by_cell: dict[Point, list[str]] = {}
        for rid, point in chosen.items():
            by_cell.setdefault(point, []).append(rid)
        losers = set()
        for point, ids in by_cell.items():
            if len(ids) == 1:
                continue
            stationary = next((rid for rid in ids if origins[rid] == point), None)
            winner = stationary or max(ids, key=lambda rid: (candidates[rid][0][0], rid))
            losers.update(set(ids) - {winner})
        owners = {point: rid for rid, point in origins.items()}
        for rid, point in chosen.items():
            other = owners.get(point)
            if other is not None and rid != other and chosen[other] == origins[rid]:
                losers.update((rid, other))
        if not losers:
            return chosen, rejected
        for rid in losers:
            # Once a robot selects wait it has priority over any incoming robot.
            candidates[rid].pop(0)
            chosen[rid] = candidates[rid][0][1]
        rejected += len(losers)
