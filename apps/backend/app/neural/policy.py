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
from app.domain.models import (
    NO_PROGRESS_TICK_LIMIT,
    CellType,
    Point,
    Robot,
    SimulationState,
    TransportTask,
    Warehouse,
)
from app.neural.coordination import CoordinationWeights, QueueTrigger
from app.scheduling.assignment import energy_needed

Mode = Literal["task", "charge", "park", "idle", "move"]
ChargingWeights = tuple[float, float, float, int, float]
KINDS = ("task", "charge", "park", "idle", "move")
# Dispatch and motion share the network. Feature slots beyond the common
# context are specific to their decision type.
FEATURE_VERSION = 1
FEATURE_COUNT = 44
DISPATCH_AGE_CAP = 400
MAX_DISPATCH_FLEET_CONTEXT = 20
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
    narrow_passage: bool = False
    wait_streak: int = 0
    charging: "ChargingFeatures | None" = None
    stalled_ticks: int = 0
    coordinating: bool = False


@dataclass(frozen=True)
class ChargingFeatures:
    battery: float
    travel_energy: float
    nearest_energy: float
    move_energy: float
    continuing: bool
    redirecting: bool = False


class Policy(Protocol):
    id: str

    def scores(self, actions: Sequence[Action]) -> list[float]: ...


def weight_id(
    layers: list[dict[str, Any]],
    passage_weights: list[float] | None = None,
    waiting_weights: tuple[int, float] | None = None,
    charging_weights: ChargingWeights | None = None,
    coordination_weights: CoordinationWeights | None = None,
) -> str:
    payload: list[Any] = layers if passage_weights is None else [layers, passage_weights]
    if waiting_weights is not None:
        payload = [layers, passage_weights, waiting_weights]
    if charging_weights is not None:
        payload = [layers, passage_weights, waiting_weights, charging_weights]
    if coordination_weights is not None:
        # Preserve the hashes of checkpoints written before the optional queue trigger.
        profile = (
            coordination_weights[:-1] if coordination_weights[-1] is None else coordination_weights
        )
        payload = [layers, passage_weights, waiting_weights, charging_weights, profile]
    digest = hashlib.sha256(json.dumps(payload, separators=(",", ":")).encode()).hexdigest()
    return f"nn-{digest[:12]}"


class NeuralPolicy:
    def __init__(self, artifact: dict[str, Any]):
        if artifact["feature_version"] != FEATURE_VERSION:
            raise ValueError("Model neuronového řízení používá jinou verzi vstupů.")
        payload = artifact["layers"]
        passage_weights = artifact.get("passage_weights")
        waiting_weights = artifact.get("waiting_weights")
        charging_weights = artifact.get("charging_weights")
        coordination_weights = artifact.get("coordination_weights")
        self.feature_version = FEATURE_VERSION
        if artifact["id"] != weight_id(
            payload, passage_weights, waiting_weights, charging_weights, coordination_weights
        ):
            raise ValueError("Váhy neuronového řízení neodpovídají identifikátoru modelu.")
        self.id = artifact["id"]
        self.artifact = artifact
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
        self.passage_weights: NDArray[np.float64] | None = None
        if passage_weights is not None:
            weights = np.asarray(passage_weights, dtype=np.float64)
            if weights.shape != (self.layers[-1][0].shape[0],) or not np.isfinite(weights).all():
                raise ValueError("Neplatné váhy neuronové sítě pro úzké průjezdy.")
            self.passage_weights = weights
        self.waiting_weights: tuple[int, float] | None = None
        if waiting_weights is not None:
            threshold, penalty = waiting_weights
            if (
                type(threshold) is not int
                or threshold < 1
                or not np.isfinite(penalty)
                or penalty <= 0
            ):
                raise ValueError("Neplatné váhy neuronové sítě pro dlouhé čekání v uličce.")
            self.waiting_weights = threshold, penalty
        self.charging_weights: ChargingWeights | None = None
        if charging_weights is not None:
            reserve, urgency, distance, retry, redirect_distance = charging_weights
            if (
                not np.isfinite([reserve, urgency, distance, redirect_distance]).all()
                or min(reserve, urgency, distance, redirect_distance) < 0
                or type(retry) is not int
                or retry < 0
            ):
                raise ValueError("Neplatné váhy neuronové sítě pro výběr nabíječky.")
            self.charging_weights = reserve, urgency, distance, retry, redirect_distance
        self.coordination_weights: CoordinationWeights | None = None
        if coordination_weights is not None:
            profile = CoordinationWeights(*coordination_weights)
            if profile.queue_trigger is not None:
                queue = QueueTrigger(*profile.queue_trigger)
                if (
                    any(
                        type(value) is not int
                        for value in (queue.robots, queue.wait_ticks, queue.delivery_delay)
                    )
                    or queue.robots < 2
                    or min(queue.wait_ticks, queue.delivery_delay) < 1
                    or not 0 <= queue.fraction_complete <= 1
                ):
                    raise ValueError("Neplatná pravidla neuronové sítě pro rozpoznání fronty.")
                profile = profile._replace(queue_trigger=queue)
            integer_values = (
                profile.stalled_ticks,
                profile.duration,
                profile.delivery_delay,
                profile.cooldown,
            )
            numeric_values = (profile.movement, profile.progress, profile.revisit, profile.baseline)
            if (
                any(type(x) is not int or x < 0 for x in integer_values)
                or not 0 < profile.stalled_ticks < NO_PROGRESS_TICK_LIMIT
                or not profile.duration
                or not np.isfinite(numeric_values).all()
                or min(numeric_values) < 0
                or not 0 <= profile.fraction_complete <= 1
                or type(profile.prefer_waiting_robots) is not bool
                or type(profile.release_pickups) is not bool
            ):
                raise ValueError("Neplatné váhy neuronové sítě pro koordinaci front.")
            self.coordination_weights = profile

    def scores(self, actions: Sequence[Action]) -> list[float]:
        values = np.asarray([a.values for a in actions], dtype=np.float64)
        for weights, bias in self.layers[:-1]:
            values = np.maximum(values @ weights + bias, 0)
        weights, bias = self.layers[-1]
        if self.passage_weights is not None and actions[0].narrow_passage:
            weights = weights + self.passage_weights[:, None]
        scores: list[float] = (values @ weights + bias).ravel().tolist()
        if self.waiting_weights is not None and not actions[0].narrow_passage:
            threshold, penalty = self.waiting_weights
            for index, action in enumerate(actions):
                if action.wait_streak >= threshold:
                    scores[index] -= penalty
        if self.charging_weights is not None and actions[0].kind != "move":
            for index, action in enumerate(actions):
                if action.charging is not None:
                    scores[index] += charging_score(action.charging, self.charging_weights)
        profile = self.coordination_weights
        if profile is None or not actions[0].coordinating:
            return scores
        origin = actions[0].target
        age = min(1.0, actions[0].wait_streak / 24)
        movement = profile.movement * (0.2 + 0.8 * age if profile.prefer_waiting_robots else 1.0)
        return [
            profile.baseline * score
            + movement * (action.target != origin)
            + profile.progress * action.distance_gain
            - profile.revisit * action.recent_visits
            for action, score in zip(actions, scores, strict=True)
        ]


def charging_score(features: ChargingFeatures, weights: ChargingWeights) -> float:
    reserve, urgency, distance, _, redirect_distance = weights
    margin = features.battery - features.nearest_energy
    # ReLU units for departure urgency and the cost of a longer available trip.
    early = max(0.0, reserve - margin) / 20
    exposure = max(0.0, min(1.0, (2 * reserve - margin) / max(reserve, 1.0)))
    detour = (features.travel_energy - features.nearest_energy) / max(32 * features.move_energy, 1)
    if features.redirecting:
        return urgency * early - redirect_distance * detour + 0.5 * features.continuing
    return urgency * early - distance * exposure * detour + 0.5 * features.continuing


def narrow_passage_cells(warehouse: Warehouse) -> set[Point]:
    try:
        rows = json.loads(warehouse.metadata.get("passage_rows", "[]"))
        generator = json.loads(warehouse.metadata.get("generator", "{}"))
    except json.JSONDecodeError:
        return set()
    if not isinstance(rows, list) or not isinstance(generator, dict):
        return set()
    if generator.get("passage_width") != 1:
        return set()
    middle = warehouse.width // 2
    return {
        (x, y)
        for row in rows
        if isinstance(row, int) and 0 <= row < warehouse.height
        for y in range(max(0, row - 1), min(warehouse.height, row + 2))
        for x in range(middle - 2, middle + 2)
    }


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
    fleet_size = len(state.robots)
    if kind != "move":
        # Saturate the dispatch input where the model still ranks feasible work above idle.
        fleet_size = min(fleet_size, MAX_DISPATCH_FLEET_CONTEXT)
    return (
        *(float(kind == name) for name in KINDS),
        robot.battery / robot.battery_capacity,
        min(robot.battery / 200, 2),
        robot.load / robot.capacity,
        fleet_size / 32,
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
    *,
    charging_grid: Grid | None = None,
    current_charge: Point | None = None,
) -> list[Action]:
    actions = []
    eligible = []
    for task in pending if current_charge is None else ():
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
                        min(state.tick - task.created_tick, DISPATCH_AGE_CAP) / 200,
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

    options: list[tuple[Point, int, int, Mode]] = []
    for point in dict.fromkeys([*grid.chargers, robot.home]):
        if (
            point is None
            or (point in goals and point != current_charge)
            or point in stations
            or point in occupied
        ):
            continue
        distance = grid.distance(robot.position, point)
        if distance is None or distance * state.config.move_energy > robot.battery:
            continue
        is_charger = grid.kind(point) == CellType.CHARGER
        if is_charger and robot.battery < robot.battery_capacity:
            kind: Mode = "charge"
        elif point == robot.home and distance and current_charge is None:
            kind = "park"
        else:
            continue
        routed = distance
        if kind == "charge" and charging_grid is not None and point != robot.position:
            reachable = charging_grid.distance(robot.position, point)
            if reachable is None or reachable * state.config.move_energy > robot.battery + 1e-9:
                continue
            routed = reachable
        options.append((point, distance, routed, kind))
    if current_charge is not None:
        planned = next((routed for point, _, routed, _ in options if point == current_charge), None)
        if planned is not None:
            options = [
                option
                for option in options
                if option[0] == current_charge or option[2] + 2 <= planned
            ]
    nearest = min((routed for _, _, routed, kind in options if kind == "charge"), default=0)
    energy = state.config.move_energy
    for point, distance, routed, kind in options:
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
                        float(grid.kind(point) == CellType.CHARGER),
                        float(distance == 0),
                    ),
                ),
                charging=ChargingFeatures(
                    robot.battery,
                    routed * energy,
                    nearest * energy,
                    energy,
                    point == current_charge,
                    current_charge is not None,
                )
                if kind == "charge"
                else None,
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
    narrow_passage: bool = False,
    wait_streak: int = 0,
    stalled_ticks: int = 0,
    coordinating: bool = False,
    charging: bool = False,
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
    route_remaining = dynamic if dynamic is not None else current
    energy = state.config.move_energy
    protected_distance = (
        route_remaining
        if charging
        and energy > 0
        and route_remaining is not None
        and robot.battery - route_remaining * energy <= state.config.critical_threshold
        else None
    )
    actions = []
    points = [origin, *open_grid.neighbors(origin)]
    for point in points:
        if point != origin and robot.battery + 1e-9 < energy:
            continue
        distance = grid.distance(point, goal)
        dynamic_next = open_grid.distance(point, goal)
        if protected_distance is not None and point != origin:
            # Keep the last battery reserve for reaching the charger. Wait if
            # traffic prevents a step along a shortest available route.
            next_remaining = dynamic_next if dynamic is not None else distance
            if next_remaining is None or next_remaining >= protected_distance:
                continue
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
                narrow_passage=narrow_passage,
                wait_streak=wait_streak if point == origin else 0,
                stalled_ticks=stalled_ticks,
                coordinating=coordinating,
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
