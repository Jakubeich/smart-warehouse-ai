"""Pure synchronous tick engine; no wall clock pacing, network, database or renderer."""

from collections import deque
from dataclasses import asdict, dataclass
from math import atan2, degrees
from time import perf_counter
from typing import Any
from uuid import uuid4

from app.algorithms.mapf import PlanResult, plan
from app.core.generator import layout_key
from app.domain.grid import Grid
from app.domain.models import (
    DEFAULT_MAX_TICKS,
    NO_PROGRESS_TICK_LIMIT,
    AssignmentCandidate,
    AssignmentDecision,
    CellType,
    Event,
    NeuralDecision,
    Point,
    Robot,
    RobotStatus,
    Scenario,
    SimulationState,
    TaskStatus,
    TransportTask,
)
from app.learning.features import FEATURE_NAMES, FEATURE_VERSION, features, geometric_eta
from app.learning.model import EtaModel
from app.neural.coordination import CoordinationWeights, simultaneous_moves
from app.neural.online import Experience, ExperienceBuffer
from app.neural.policy import (
    DISPATCH_AGE_CAP,
    Action,
    Policy,
    dispatch_actions,
    load_policy,
    motion_actions,
    narrow_passage_cells,
    resolve_moves,
)
from app.scheduling.assignment import assign, feasible
from app.simulation.invariants import (
    TRANSITIONS,
    InvariantError,
    validate_state,
    validate_transition,
)

RECENT_FLEET_STATES = 256
TRAINING_STALL_TICKS = 120
TICK_LIMIT_MESSAGE = "Simulation step limit reached."
TRAINING_STALL_MESSAGE = "Most available robots are blocked and no deliveries were completed."


@dataclass(frozen=True)
class RouteProgress:
    leg: tuple[str, str | None]
    target: Point
    best_distance: int | None
    last_tick: int


class Engine:
    def __init__(
        self,
        scenario: Scenario,
        simulation_id: str,
        predictor: EtaModel | None = None,
        *,
        policy: Policy | None = None,
        experience: ExperienceBuffer | None = None,
    ):
        self.policy = (policy or load_policy()) if scenario.config.control == "neural" else None
        if self.policy and scenario.config.neural_model_id not in {None, self.policy.id}:
            raise ValueError("Požadovaná verze neuronové sítě není dostupná.")
        self.experience = experience
        self.visits: dict[str, deque[Point]] = {r.id: deque(maxlen=12) for r in scenario.robots}
        self.motion_waits: dict[str, int] = {}
        self.motion_grid: Grid | None = None
        self.charging_grid: Grid | None = None
        self.neural_charging: set[str] = set()
        self.last_delivery_tick = 0
        self.coordination_until = 0
        self.active_coordination: CoordinationWeights | None = None
        if self.policy is None and scenario.config.scheduler == "learned" and predictor is None:
            raise ValueError("ML přiřazování vyžaduje natrénovaný model.")
        self.predictor = predictor
        self.episode_id = str(uuid4())
        self.observations: list[dict[str, Any]] = []
        self.pending_observations: dict[str, dict[str, Any]] = {}
        if any(
            r.mode != "IDLE"
            or r.task_id
            or r.service_remaining
            or r.distance
            or r.status != RobotStatus.IDLE
            for r in scenario.robots
        ):
            raise ValueError("A scenario must contain initial idle robot configurations")
        if any(
            t.status != TaskStatus.PENDING or t.assigned_robot or t.created_tick != 0
            for t in scenario.tasks
        ):
            raise ValueError("A scenario must contain initial pending tasks created at tick zero")
        self.initial = scenario.model_copy(deep=True)
        self.max_ticks = scenario.config.max_ticks or DEFAULT_MAX_TICKS
        self.initial.config.max_ticks = self.max_ticks
        self.tick_limit_reached = False
        if self.policy:
            self.initial.config.neural_model_id = self.policy.id
            self.initial.config.ml_model_id = None
        elif predictor and self.initial.config.scheduler == "learned":
            self.initial.config.ml_model_id = predictor.id
        self.state = SimulationState(
            id=simulation_id,
            scenario_id=scenario.id,
            name=scenario.name,
            warehouse=scenario.warehouse.model_copy(deep=True),
            robots=[r.model_copy(deep=True) for r in scenario.robots],
            tasks=[t.model_copy(deep=True) for t in scenario.tasks],
            seed=scenario.seed,
            config=self.initial.config.model_copy(deep=True),
        )
        for r in self.state.robots:
            r.home = r.home or r.position
            r.path = [r.position]
        self.grid = Grid(self.state.warehouse)
        self.narrow_passages = narrow_passage_cells(self.state.warehouse)
        self.dirty = True
        self.stalled_ticks = 0
        self.repeated_fleet_states: dict[tuple[object, ...], int] = {}
        self.training_route_progress: dict[str, RouteProgress] = {}
        validate_state(self.state)
        self.emit("STATE_SNAPSHOT", f"Scenario initialized. {len(self.state.robots)} robots ready.")

    def emit(self, kind: str, message: str, entity: str | None = None) -> None:
        self.state.events.append(
            Event(tick=self.state.tick, type=kind, message=message, entity_id=entity)
        )
        self.state.events = self.state.events[-500:]

    def set_status(self, robot: Robot, status: RobotStatus) -> None:
        if robot.status == status:
            return
        if (
            status not in {RobotStatus.BLOCKED, RobotStatus.ERROR}
            and status not in TRANSITIONS[robot.status]
        ):
            raise InvariantError(f"Invalid robot transition {robot.status} → {status}")
        robot.status = status

    def fail(self, reason: str) -> None:
        self.state.status = "FAILED"
        self.state.error = reason
        if self.experience:
            self.experience.dispatch_failed()
        for r in self.state.robots:
            if r.mode not in {"IDLE", "OFFLINE"}:
                self.set_status(r, RobotStatus.BLOCKED)
        self.emit("SIMULATION_ERROR", reason)

    def _dispatch(self) -> None:
        active = [
            t for t in self.state.tasks if t.status in {TaskStatus.ASSIGNED, TaskStatus.IN_PROGRESS}
        ]
        claimed = {p for t in active for p in (t.pickup, t.dropoff)}
        pending = sorted(
            (t for t in self.state.tasks if t.status == TaskStatus.PENDING),
            key=lambda t: (-t.priority, t.created_tick, t.id),
        )
        # Station admission avoids equal MAPF goals, and pickup/delivery phase deadlocks.
        batch: list[TransportTask] = []
        for task in pending:
            if task.pickup not in claimed and task.dropoff not in claimed:
                batch.append(task)
                claimed.update((task.pickup, task.dropoff))
        available = [r for r in self.state.robots if r.mode == "IDLE"]
        inputs: dict[tuple[str, str], list[float]] = {}
        predictions: dict[tuple[str, str], float] = {}
        candidates: dict[str, list[AssignmentCandidate]] = {}

        def estimate(robot: Robot, task: TransportTask) -> float:
            key = (robot.id, task.id)
            if key not in predictions:
                values = features(self.state, robot, task, self.grid)
                inputs[key] = values
                assert self.predictor is not None
                predictions[key] = self.predictor.predict(values)
                candidates.setdefault(task.id, []).append(
                    AssignmentCandidate(
                        robot_id=robot.id,
                        predicted_ticks=predictions[key],
                        geometric_ticks=geometric_eta(values),
                        route_occupied=int(
                            values[FEATURE_NAMES.index("pickup_route_occupied")]
                            + values[FEATURE_NAMES.index("delivery_route_occupied")]
                        ),
                        route_opposing_edges=int(
                            values[FEATURE_NAMES.index("route_opposing_edges")]
                        ),
                    )
                )
            return predictions[key]

        assignments = assign(
            available,
            batch,
            self.grid,
            self.state.config,
            estimate=estimate if self.predictor else None,
        )
        # Freeze inputs before mutating any chosen robot; all observations describe
        # exactly the decision-time state, never a later snapshot.
        for robot, task in assignments:
            key = (robot.id, task.id)
            values = inputs.get(key) or features(self.state, robot, task, self.grid)
            self.pending_observations[task.id] = {
                "task_id": task.id,
                "robot_id": robot.id,
                "assigned_tick": self.state.tick,
                "features": values,
                "predicted_ticks": predictions.get(key),
                "geometric_ticks": geometric_eta(values),
            }
            if self.state.config.scheduler == "learned" and self.predictor:
                self.state.assignment_decisions.append(
                    AssignmentDecision(
                        task_id=task.id,
                        robot_id=robot.id,
                        tick=self.state.tick,
                        model_id=self.predictor.id,
                        candidates=candidates[task.id],
                    )
                )
                self.state.assignment_decisions = self.state.assignment_decisions[-20:]
        for robot, task in assignments:
            task.status = TaskStatus.ASSIGNED
            task.assigned_robot = robot.id
            task.assigned_tick = self.state.tick
            robot.task_id, robot.mode, robot.goal = task.id, "PICKUP", task.pickup
            self.set_status(robot, RobotStatus.ASSIGNED)
            self.set_status(robot, RobotStatus.MOVING_TO_PICKUP)
            self.dirty = True
            self.emit("TASK_ASSIGNED", f"{task.id} assigned to {robot.id}", task.id)
        claimed_goals = {r.goal for r in self.state.robots if r.goal}
        for robot in available:
            if robot.mode != "IDLE":
                continue
            needs_charge = robot.battery < self.state.config.critical_threshold or (
                bool(pending)
                and not any(feasible(robot, t, self.grid, self.state.config) for t in pending)
                and robot.battery < robot.battery_capacity
            )
            if needs_charge:
                chargers = [
                    p
                    for p, c in self.grid.cells.items()
                    if c == CellType.CHARGER
                    and (p not in claimed_goals or p == robot.position)
                    and not any(r.id != robot.id and r.position == p for r in self.state.robots)
                    and self.grid.distance(robot.position, p) is not None
                ]
                if chargers:
                    target = min(
                        chargers,
                        key=lambda p: (
                            p != robot.home,
                            self.grid.distance(robot.position, p) or 0,
                            p,
                        ),
                    )
                    robot.mode, robot.goal = "RETURN", target
                    self.set_status(robot, RobotStatus.WAITING)
                    claimed_goals.add(target)
                    self.dirty = True

    def _neural_dispatch(self) -> None:
        assert self.policy is not None
        s = self.state
        pending = [task for task in s.tasks if task.status == TaskStatus.PENDING]
        stations = {
            p
            for task in s.tasks
            if task.status in {TaskStatus.ASSIGNED, TaskStatus.IN_PROGRESS}
            for p in (task.pickup, task.dropoff)
            if p == task.dropoff
            or task.status == TaskStatus.ASSIGNED
            or self.active_coordination is None
            or not self.active_coordination.release_pickups
        }
        goals = {r.goal for r in s.robots if r.goal is not None}
        occupants = {r.position for r in s.robots}
        charging_weights = getattr(self.policy, "charging_weights", None)
        redirect: dict[str, Point] = {}
        charging_grid = None
        if charging_weights is not None:
            reserve, _, _, retry, _ = charging_weights
            blocked_goals = {
                r.position
                for r in s.robots
                if r.mode == "OFFLINE" or r.battery + 1e-9 < s.config.move_energy
            }
            if retry:
                for r in s.robots:
                    goal = r.goal
                    if r.id not in self.neural_charging or goal is None or goal == r.position:
                        continue
                    remaining = self.grid.distance(r.position, goal)
                    if r.battery + 1e-9 < s.config.move_energy:
                        continue
                    margin = (
                        r.battery - remaining * s.config.move_energy
                        if remaining is not None
                        else -1
                    )
                    if (
                        goal in blocked_goals
                        or margin < reserve / 2
                        or (margin < reserve and self.motion_waits.get(r.id, 0) >= retry)
                    ):
                        redirect[r.id] = goal
            if redirect or any(r.mode == "IDLE" for r in s.robots):
                occupied_route = blocked_goals | {
                    r.position for r in s.robots if r.mode == "CHARGE" or r.service_remaining
                }
                if (
                    self.charging_grid is None
                    or self.charging_grid.blocked != self.grid.blocked | occupied_route
                ):
                    self.charging_grid = Grid(s.warehouse, set(s.obstacles) | occupied_route)
                charging_grid = self.charging_grid
        available = [
            r for r in sorted(s.robots, key=lambda r: r.id) if r.mode == "IDLE" or r.id in redirect
        ]
        # Rank actions for all available robots in one batch, then claim
        # robots and stations in score order.
        candidates = [
            (robot, action)
            for robot in available
            for action in dispatch_actions(
                s,
                self.grid,
                robot,
                pending,
                stations,
                goals,
                occupants - {robot.position},
                charging_grid=charging_grid,
                current_charge=redirect.get(robot.id),
            )
        ]
        if not candidates:
            return
        scores = self.policy.scores([action for _, action in candidates])
        best_idle = {
            robot.id: score
            for (robot, action), score in zip(candidates, scores, strict=True)
            if action.kind == "idle"
        }
        chosen_robots = set()
        ranked = sorted(zip(scores, candidates, strict=True), key=lambda pair: -pair[0])
        for score, (robot, action) in ranked:
            if robot.id in chosen_robots or score <= best_idle[robot.id]:
                continue
            previous_charge = redirect.get(robot.id)
            if previous_charge == action.target:
                chosen_robots.add(robot.id)
                continue
            if action.task:
                if {action.task.pickup, action.task.dropoff} & (stations | goals):
                    continue
            elif action.target in goals or action.target in stations:
                continue
            chosen_robots.add(robot.id)
            if self.experience:
                distance: float = self.grid.distance(robot.position, action.target) or 0
                if action.task:
                    distance += (
                        (self.grid.distance(action.task.pickup, action.task.dropoff) or 0)
                        + action.task.load_duration
                        + action.task.unload_duration
                    )
                elif action.kind == "charge":
                    distance += (robot.battery_capacity - robot.battery) / s.config.charging_rate
                self.experience.dispatch_started(robot.id, action.values, s.tick, distance + 1)
            s.neural_decisions.append(
                NeuralDecision(
                    robot_id=robot.id,
                    action=action.kind,
                    target=action.target,
                    task_id=action.task.id if action.task else None,
                    score=score,
                )
            )
            if action.task:
                task = action.task
                stations.update((task.pickup, task.dropoff))
                task.status, task.assigned_robot, task.assigned_tick = (
                    TaskStatus.ASSIGNED,
                    robot.id,
                    s.tick,
                )
                robot.task_id, robot.mode, robot.goal = task.id, "PICKUP", task.pickup
                self.set_status(robot, RobotStatus.ASSIGNED)
                self.set_status(robot, RobotStatus.MOVING_TO_PICKUP)
                self.emit("TASK_ASSIGNED", f"{task.id} assigned to {robot.id}", task.id)
            else:
                if previous_charge is not None:
                    goals.discard(previous_charge)
                robot.mode, robot.goal = "RETURN", action.target
                if action.kind == "charge":
                    self.neural_charging.add(robot.id)
                self.set_status(robot, RobotStatus.WAITING)
            goals.add(action.target)

        if (
            self.experience
            and self.stalled_ticks
            and not chosen_robots
            and all(robot.mode in {"IDLE", "OFFLINE"} for robot in s.robots)
        ):
            # Waiting is negative feedback only when the whole fleet declined feasible work.
            with_work = {robot.id for robot, action in candidates if action.task is not None}
            for robot, action in candidates:
                if action.kind == "idle" and robot.id in with_work:
                    self.experience.dispatch.append(Experience(action.values, -0.4))

    def _coordinate_traffic(self) -> None:
        profile: CoordinationWeights | None = getattr(self.policy, "coordination_weights", None)
        if profile is None:
            self.active_coordination = None
            return
        s = self.state
        if (
            self.stalled_ticks >= profile.stalled_ticks
            and s.metrics.completed_tasks >= profile.fraction_complete * len(s.tasks)
        ):
            self.coordination_until = max(self.coordination_until, s.tick + profile.duration)
        if (
            self.coordination_until
            and profile.delivery_delay
            and s.tick - self.last_delivery_tick >= profile.delivery_delay
            and s.tick >= self.coordination_until + profile.cooldown
        ):
            self.coordination_until = s.tick + profile.duration
        queue = profile.queue_trigger
        if (
            queue is not None
            and s.metrics.completed_tasks >= queue.fraction_complete * len(s.tasks)
            and s.tick >= self.coordination_until + profile.cooldown
            and s.tick - self.last_delivery_tick >= queue.delivery_delay
            and sum(streak >= queue.wait_ticks for streak in self.motion_waits.values())
            >= queue.robots
        ):
            self.coordination_until = s.tick + profile.duration
        self.active_coordination = profile if s.tick < self.coordination_until else None

    def _neural_moves(self) -> tuple[dict[str, Point], list[Experience]]:
        assert self.policy is not None
        s = self.state
        occupants = {r.position: r for r in s.robots}
        fixed = {
            r.position
            for r in s.robots
            if r.goal in {None, r.position}
            or r.service_remaining
            or r.mode == "OFFLINE"
            or r.battery + 1e-9 < s.config.move_energy
        }
        blocked = self.grid.blocked | fixed
        if self.motion_grid is None or self.motion_grid.blocked != blocked:
            self.motion_grid = Grid(s.warehouse, set(s.obstacles) | fixed)
        ranked: dict[str, list[tuple[float, Point]]] = {}
        candidates: dict[str, dict[Point, Action]] = {}
        profile = self.active_coordination
        coordinating = bool(profile and (profile.movement or profile.progress or profile.revisit))
        for robot in s.robots:
            actions = motion_actions(
                s,
                self.grid,
                self.motion_grid,
                robot,
                occupants,
                self.visits[robot.id],
                narrow_passage=robot.position in self.narrow_passages,
                wait_streak=self.motion_waits.get(robot.id, 0),
                stalled_ticks=self.stalled_ticks,
                coordinating=coordinating,
                charging=robot.id in self.neural_charging,
            )
            if not actions:
                continue
            scores = self.policy.scores(actions)
            candidates[robot.id] = {action.target: action for action in actions}
            ranked[robot.id] = sorted(
                ((score, action.target) for score, action in zip(scores, actions, strict=True)),
                key=lambda candidate: -candidate[0],
            )
        old = {robot.id: robot.position for robot in s.robots}
        together = simultaneous_moves(old, ranked) if coordinating else None
        if together is None:
            new, rejected = resolve_moves(old, ranked)
        else:
            new = together
            rejected = sum(choices[0][1] != new[robot] for robot, choices in ranked.items())
        self.motion_waits = {
            rid: self.motion_waits.get(rid, 0) + 1 for rid in ranked if old[rid] == new[rid]
        }
        s.neural_rejections += rejected
        feedback: list[Experience] = []
        entered = {cell for rid, cell in new.items() if cell != old[rid]}
        for rid, choices in ranked.items():
            if self.experience:
                first = choices[0][1]
                if first != new[rid] and first != old[rid]:
                    feedback.append(Experience(candidates[rid][first].values, -0.7))
                selected = candidates[rid][new[rid]]
                if new[rid] != old[rid]:
                    robot = occupants[old[rid]]
                    reward = (
                        1.0
                        if new[rid] == robot.goal
                        else 0.15 + 0.3 * selected.distance_gain - 0.6 * selected.recent_visits
                    )
                    # Credit giving way when a second robot actually used the vacated cell.
                    if old[rid] in entered and (coordinating or selected.distance_gain <= 0):
                        reward = max(reward, 0.55 - 0.2 * selected.recent_visits)
                else:
                    # A forced wait says nothing about the quality of the chosen action.
                    reward = -0.1 if first == new[rid] and len(choices) > 1 else 0.0
                if reward:
                    feedback.append(Experience(selected.values, reward))
            score = next(score for score, point in choices if point == new[rid])
            s.neural_decisions.append(
                NeuralDecision(
                    robot_id=rid,
                    action="wait" if old[rid] == new[rid] else "move",
                    target=new[rid],
                    score=score,
                )
            )
        return new, feedback

    def _plan(self) -> bool:
        s = self.state
        starts = {r.id: r.position for r in s.robots}
        goals = {
            r.id: r.goal if r.goal is not None and r.service_remaining == 0 else r.position
            for r in s.robots
        }
        moving = [
            r
            for r in s.robots
            if goals[r.id] != r.position
            and r.mode != "OFFLINE"
            and r.battery + 1e-9 >= s.config.move_energy
        ]
        stationary = {r.position for r in s.robots if r not in moving}
        planning_grid = Grid(s.warehouse, set(s.obstacles) | stationary)
        ordered = sorted(
            moving, key=lambda r: (-r.waiting if s.config.planner == "adaptive" else 0, r.id)
        )
        try:
            if moving:
                result = plan(
                    planning_grid,
                    {r.id: starts[r.id] for r in moving},
                    {r.id: goals[r.id] for r in moving},
                    s.config.planner,
                    horizon=s.config.horizon,
                    max_nodes=s.config.max_nodes,
                    timeout=s.config.timeout_seconds,
                    order=[r.id for r in ordered],
                )
            else:
                result = PlanResult("SUCCESS")
        except ValueError as exc:
            self.fail(str(exc))
            return False
        s.metrics.planning_time_ms += result.elapsed_ms
        s.metrics.replans += 1
        s.metrics.planning_conflicts += result.conflicts
        s.planner_status = result.status
        s.conflicts = [asdict(result.first_conflict)] if result.first_conflict else []
        if result.status != "SUCCESS":
            self.fail(f"{s.config.planner}: {result.status}. {result.reason}")
            return False
        for r in s.robots:
            r.path, r.path_index = result.paths.get(r.id, [r.position]), 0
        self.dirty = False
        self.emit("PATH_REPLANNED", f"Global plan: {s.config.planner}, cost {result.cost}.")
        return True

    def step(self) -> SimulationState:
        s = self.state
        if s.status in {"COMPLETED", "FAILED", "STOPPED"}:
            return s
        old = {r.id: r.position for r in s.robots}
        feedback: list[Experience] = []
        if self.policy:
            since = perf_counter()
            s.neural_decisions = []
            s.neural_last_model_id = self.policy.id
            self._coordinate_traffic()
            self._neural_dispatch()
            new, feedback = self._neural_moves()
            s.metrics.planning_time_ms += (perf_counter() - since) * 1000
        else:
            self._dispatch()
            if self.dirty and not self._plan():
                return s
            new = {r.id: r.path[min(r.path_index + 1, len(r.path) - 1)] for r in s.robots}
        validate_transition(self.grid, old, new)
        # Reject an infeasible move before applying any part of the transition.
        for r in s.robots:
            if new[r.id] != r.position and r.battery + 1e-9 < s.config.move_energy:
                self.fail(f"{r.id}: insufficient energy; transition rejected")
                return s
        if self.experience:
            self.experience.motion.extend(feedback)
        s.tick += 1
        progressed = False
        for r in s.robots:
            had_movement_energy = r.battery + 1e-9 >= s.config.move_energy
            moved = new[r.id] != r.position
            was_servicing = r.service_remaining > 0 and r.battery + 1e-9 >= s.config.handling_energy
            if moved:
                r.orientation = round(
                    degrees(atan2(new[r.id][1] - r.position[1], new[r.id][0] - r.position[0]))
                )
                r.position = new[r.id]
                r.distance += 1
                r.battery = max(0, r.battery - s.config.move_energy)
                progressed = True
            elif r.mode != "CHARGE":
                r.battery = max(
                    0,
                    r.battery
                    - (s.config.handling_energy if was_servicing else s.config.wait_energy),
                )
                if r.mode in {"PICKUP", "DROPOFF", "RETURN"} and not was_servicing:
                    r.waiting += 1
            if self.policy:
                self.visits[r.id].append(old[r.id])
                r.path, r.path_index = [r.position], 0
            else:
                r.path_index = min(r.path_index + 1, len(r.path) - 1)
                if had_movement_energy and r.battery + 1e-9 < s.config.move_energy:
                    self.dirty = True
            if r.mode not in {"IDLE", "OFFLINE"}:
                r.busy_ticks += 1
            key = f"{r.position[0]},{r.position[1]}"
            s.heatmap[key] = s.heatmap.get(key, 0) + 1
            task = next((t for t in s.tasks if t.id == r.task_id), None)
            if was_servicing and task:
                r.service_remaining -= 1
                progressed = True
                if r.service_remaining == 0:
                    if r.mode == "PICKUP":
                        task.pickup_tick = s.tick
                        task.status = TaskStatus.IN_PROGRESS
                        r.load = task.payload_weight
                        r.mode, r.goal = "DROPOFF", task.dropoff
                        self.set_status(r, RobotStatus.MOVING_TO_DROPOFF)
                    else:
                        task.status, task.completed_tick = TaskStatus.COMPLETED, s.tick
                        self.last_delivery_tick = s.tick
                        observation = self.pending_observations.pop(task.id, None)
                        if observation is not None:
                            self.observations.append(
                                {
                                    **observation,
                                    "completed_tick": s.tick,
                                    "actual_ticks": s.tick - observation["assigned_tick"],
                                }
                            )
                        if self.experience:
                            self.experience.dispatch_finished(r.id, s.tick)
                        r.completed_tasks += 1
                        r.load, r.task_id = 0, None
                        if self.policy:
                            r.mode, r.goal = "IDLE", None
                            self.set_status(r, RobotStatus.IDLE)
                        else:
                            r.mode, r.goal = "RETURN", r.home
                            self.set_status(r, RobotStatus.WAITING)
                        self.emit("TASK_COMPLETED", f"{task.id} delivered by {r.id}", task.id)
                    self.dirty = True
            elif r.mode == "CHARGE":
                r.battery = min(r.battery_capacity, r.battery + s.config.charging_rate)
                progressed = True
                if r.battery >= r.battery_capacity:
                    if self.experience:
                        self.experience.dispatch_finished(r.id, s.tick)
                    r.mode, r.goal = "IDLE", None
                    self.set_status(r, RobotStatus.IDLE)
                    self.dirty = True
            elif r.goal == r.position:
                if r.mode == "RETURN":
                    if (
                        self.grid.kind(r.position) == CellType.CHARGER
                        and r.battery < r.battery_capacity
                        and (self.policy is None or r.id in self.neural_charging)
                    ):
                        r.mode, r.goal = "CHARGE", None
                        self.set_status(r, RobotStatus.CHARGING)
                        progressed = True
                    else:
                        if self.experience:
                            self.experience.dispatch_finished(r.id, s.tick)
                        r.mode, r.goal = "IDLE", None
                        self.set_status(r, RobotStatus.IDLE)
                    self.neural_charging.discard(r.id)
                    self.dirty = True
                elif task and r.mode in {"PICKUP", "DROPOFF"} and not r.service_remaining:
                    r.service_remaining = (
                        task.load_duration if r.mode == "PICKUP" else task.unload_duration
                    )
                    self.set_status(
                        r, RobotStatus.LOADING if r.mode == "PICKUP" else RobotStatus.UNLOADING
                    )
                    self.dirty = True
        self.stalled_ticks = 0 if progressed else self.stalled_ticks + 1
        if all(t.status in {TaskStatus.COMPLETED, TaskStatus.CANCELLED} for t in s.tasks):
            s.status = "COMPLETED"
            s.metrics.success = True
            self.emit("SIMULATION_COMPLETED", "All transport tasks completed.")
        elif self.majority_stranded():
            self.fail("Most available robots are out of energy.")
        elif self.stalled_ticks >= NO_PROGRESS_TICK_LIMIT and not self.has_planned_motion():
            self.fail(
                "No progress for 30 ticks: check capacity, energy, station admission or reachability"
            )
        elif s.training_loop and s.training_loop.active and self.training_fleet_blocked():
            self.fail(TRAINING_STALL_MESSAGE)
        elif self.repeats_without_delivery():
            self.fail("The fleet is repeating the same state without completing a delivery.")
        elif s.tick >= self.max_ticks:
            # Truncate the run without treating unfinished assignments as failed decisions.
            self.tick_limit_reached = True
            s.status = "FAILED"
            s.error = TICK_LIMIT_MESSAGE
            self.emit("SIMULATION_ERROR", s.error)
        self.update_metrics()
        validate_state(s)
        return s

    def has_planned_motion(self) -> bool:
        return self.policy is None and any(
            any(point != robot.position for point in robot.path[robot.path_index + 1 :])
            for robot in self.state.robots
        )

    def stranded(self, robot: Robot) -> bool:
        return (
            robot.battery + 1e-9 < self.state.config.move_energy
            and robot.mode != "CHARGE"
            and not (
                robot.mode in {"IDLE", "RETURN"}
                and self.grid.kind(robot.position) == CellType.CHARGER
                and robot.battery < robot.battery_capacity
            )
            and not (
                robot.service_remaining
                and robot.battery + 1e-9 >= self.state.config.handling_energy
            )
        )

    def majority_stranded(self) -> bool:
        available = [robot for robot in self.state.robots if robot.mode != "OFFLINE"]
        return sum(self.stranded(robot) for robot in available) * 2 > len(available)

    def training_fleet_blocked(self) -> bool:
        s = self.state
        blocked = available = 0
        for robot in s.robots:
            if robot.mode == "OFFLINE":
                self.training_route_progress.pop(robot.id, None)
                continue
            available += 1
            if self.stranded(robot):
                self.training_route_progress.pop(robot.id, None)
                blocked += 1
                continue
            target = robot.goal
            if target is None or robot.service_remaining or robot.mode == "CHARGE":
                self.training_route_progress.pop(robot.id, None)
                continue
            leg = (robot.mode, robot.task_id)
            distance = self.grid.distance(robot.position, target)
            previous = self.training_route_progress.get(robot.id)
            if previous is None or previous.leg != leg:
                progress = RouteProgress(leg, target, distance, s.tick)
            elif previous.target != target:
                # Choosing another charger does not itself advance the robot.
                progress = RouteProgress(leg, target, distance, previous.last_tick)
            elif distance is not None and (
                previous.best_distance is None or distance < previous.best_distance
            ):
                progress = RouteProgress(leg, target, distance, s.tick)
            else:
                progress = previous
            self.training_route_progress[robot.id] = progress
            blocked += s.tick - progress.last_tick >= TRAINING_STALL_TICKS
        return (
            s.tick - self.last_delivery_tick >= TRAINING_STALL_TICKS
            and blocked * 2 > available
        )

    def repeats_without_delivery(self) -> bool:
        s = self.state
        since_delivery = s.tick - self.last_delivery_tick
        if not since_delivery:
            self.repeated_fleet_states.clear()
        if since_delivery < DISPATCH_AGE_CAP or any(
            task.status == TaskStatus.PENDING and s.tick - task.created_tick < DISPATCH_AGE_CAP
            for task in s.tasks
        ):
            return False

        # Once ages stop changing dispatch scores, compare physical state and policy inputs.
        profile = getattr(self.policy, "coordination_weights", None)
        queue = profile.queue_trigger if profile else None
        charging_weights = getattr(self.policy, "charging_weights", None)
        waiting_weights = getattr(self.policy, "waiting_weights", None)
        motion_wait_cap = max(
            24,
            queue.wait_ticks if queue else 0,
            charging_weights[3] if charging_weights else 0,
            waiting_weights[0] if waiting_weights else 0,
        )
        delivery_age_cap = max(
            DISPATCH_AGE_CAP,
            profile.delivery_delay if profile else 0,
            queue.delivery_delay if queue else 0,
        )
        signature = (
            self.policy.id if self.policy else None,
            self.stalled_ticks,
            self.dirty,
            min(since_delivery, delivery_age_cap),
            bool(self.coordination_until),
            max(0, self.coordination_until - s.tick),
            max(0, self.coordination_until + (profile.cooldown if profile else 0) - s.tick),
            tuple(
                (
                    robot.position,
                    robot.goal,
                    robot.mode,
                    robot.task_id,
                    robot.service_remaining,
                    robot.battery,
                    robot.id in self.neural_charging,
                    min(robot.waiting, 100) if self.policy else robot.waiting,
                    min(self.motion_waits.get(robot.id, 0), motion_wait_cap),
                    tuple(self.visits[robot.id])
                    if self.policy
                    else tuple(robot.path[robot.path_index :]),
                )
                for robot in s.robots
            ),
        )
        prior = self.repeated_fleet_states.pop(signature, 0)
        if len(self.repeated_fleet_states) == RECENT_FLEET_STATES:
            del self.repeated_fleet_states[next(iter(self.repeated_fleet_states))]
        self.repeated_fleet_states[signature] = prior + 1
        return prior >= 2

    def learning_episode(self, purpose: str = "live") -> dict[str, Any]:
        return {
            "id": self.episode_id,
            "run_id": self.state.id,
            "feature_version": FEATURE_VERSION,
            "purpose": purpose,
            "layout_key": layout_key(self.initial.warehouse),
            "scenario": self.initial.model_dump(mode="json"),
            "status": self.state.status,
            "tick": self.state.tick,
            "samples": list(self.observations),
            "assigned": len(self.observations) + len(self.pending_observations),
            "unfinished": len(self.pending_observations),
            "model_id": self.state.config.ml_model_id,
        }

    def update_metrics(self) -> None:
        s, m = self.state, self.state.metrics
        completed = [t for t in s.tasks if t.status == TaskStatus.COMPLETED]
        m.completed_tasks = len(completed)
        m.task_completion_rate = len(completed) / len(s.tasks) if s.tasks else 1
        m.makespan = s.tick
        m.sum_of_costs = sum(r.distance + r.waiting for r in s.robots)
        m.total_distance = sum(r.distance for r in s.robots) * s.warehouse.cell_size
        m.total_waiting = sum(r.waiting for r in s.robots)
        m.average_task_completion_time = (
            sum((t.completed_tick or 0) - t.created_tick for t in completed) / len(completed)
            if completed
            else 0
        )
        m.throughput = len(completed) / (s.tick * s.config.tick_seconds) if s.tick else 0
        s.history.append(
            {
                "tick": s.tick,
                "completed": len(completed),
                "waiting": m.total_waiting,
                "distance": m.total_distance,
                "planning_ms": m.planning_time_ms,
            }
        )
        s.history = s.history[-5000:]
        s.reservations = [
            {"robot_id": r.id, "x": p[0], "y": p[1], "tick": s.tick + i}
            for r in s.robots
            for i, p in enumerate(r.path[r.path_index : r.path_index + 16])
        ]

    def add_task(self, task: TransportTask) -> None:
        if self.state.tick >= self.max_ticks:
            raise ValueError(TICK_LIMIT_MESSAGE)
        if len(self.state.tasks) >= 500 or any(t.id == task.id for t in self.state.tasks):
            raise ValueError("Task limit reached or duplicate ID")
        if task.status != TaskStatus.PENDING or task.assigned_robot:
            raise ValueError("New tasks must be pending and unassigned")
        Scenario(
            id="validation",
            name="Validation",
            warehouse=self.state.warehouse,
            robots=self.state.robots,
            tasks=[task],
        )
        if self.grid.distance(task.pickup, task.dropoff) is None:
            raise ValueError("Dynamic obstacles disconnect stations")
        task.created_tick = self.state.tick
        self.state.tasks.append(task)
        self.repeated_fleet_states.clear()
        self.training_route_progress.clear()
        if self.state.status == "COMPLETED":
            self.state.status = "PAUSED"
            self.state.metrics.success = False
        self.dirty = True
        self.emit("TASK_CREATED", f"{task.id} added to queue", task.id)

    def obstacle(self, point: Point, remove: bool = False) -> None:
        s = self.state
        if remove:
            if point not in s.obstacles:
                raise ValueError("No dynamic obstacle at this cell")
            s.obstacles.remove(point)
        else:
            if (
                not self.grid.walkable(point)
                or self.grid.kind(point) != CellType.FLOOR
                or any(r.position == point or r.home == point for r in s.robots)
            ):
                raise ValueError("Obstacles require an empty floor cell, away from robot homes")
            s.obstacles.append(point)
        self.grid = Grid(s.warehouse, set(s.obstacles))
        self.repeated_fleet_states.clear()
        self.training_route_progress.clear()
        for r in s.robots:
            r.path, r.path_index = [r.position], 0
        s.reservations = []
        self.dirty = True
        self.emit(
            "OBSTACLE_REMOVED" if remove else "OBSTACLE_ADDED",
            f"Cell {point} changed; global replanning required",
        )

    def set_available(self, robot_id: str, available: bool) -> None:
        robot = next((r for r in self.state.robots if r.id == robot_id), None)
        if robot is None:
            raise ValueError("Unknown robot")
        if robot.task_id or robot.mode not in {"IDLE", "OFFLINE"}:
            raise ValueError("Only an idle robot can change availability")
        robot.mode = "IDLE" if available else "OFFLINE"
        self.repeated_fleet_states.clear()
        self.dirty = True
        self.emit(
            "ROBOT_UPDATED", f"{robot_id} {'available' if available else 'offline'}", robot_id
        )
