"""Evaluate a fixed neural policy per attempt and retain verified improvements."""

import hashlib
import json
from collections import deque
from collections.abc import Sequence
from threading import Lock
from typing import Any

import numpy as np
from pydantic import Field

from app.domain.models import (
    DEFAULT_MAX_TICKS,
    NO_PROGRESS_TICK_LIMIT,
    Model,
    Point,
    Scenario,
    SimulationState,
)
from app.neural.coordination import CoordinationWeights
from app.neural.online import Experience, update
from app.neural.policy import (
    KINDS,
    MAX_DISPATCH_FLEET_CONTEXT,
    Action,
    ChargingFeatures,
    ChargingWeights,
    NeuralPolicy,
    narrow_passage_cells,
    weight_id,
)
from app.persistence.database import Repository

RECENT_POLICIES = 2048
RECORD_KIND = "neural_scenario_best"
promotion_lock = Lock()
STEPS = (0.002, 0.006, 0.015, 0.035, 0.045, 0.07, 0.14, 0.2, 0.27, 0.5, 0.85, 1.3)
WAIT_AGES = (96, 80, 112, 128, 64, 144, 160, 56, 184, 200, 240)
MIN_WAIT_AGE = min(WAIT_AGES)
MOTION_FEATURE = KINDS.index("move")

Preference = tuple[tuple[float, ...], tuple[float, ...]]
ChargingExample = tuple[float, float, bool]


class TrainingMemory(Model):
    source_layout: str | None = None
    attempts: int = 0
    evaluated: list[str] = Field(default_factory=list)
    motion: list[Experience] = Field(default_factory=list)
    dispatch: list[Experience] = Field(default_factory=list)
    charging: list[ChargingExample] = Field(default_factory=list)
    coordination: list[float] = Field(default_factory=list)
    queued_fleet: list[int] = Field(default_factory=list)
    aisle: list[tuple[int, float]] = Field(default_factory=list)
    passage: list[Preference] = Field(default_factory=list)

    def record(self, trial: "TrainingTrial") -> "TrainingMemory":
        if trial.id in self.evaluated:
            return self
        return TrainingMemory(
            attempts=self.attempts + 1,
            evaluated=[*self.evaluated[-(RECENT_POLICIES - 1):], trial.id],
            motion=[*self.motion, *trial.motion_samples][-384:],
            dispatch=[*self.dispatch, *trial.dispatch_samples][-192:],
            charging=[*self.charging, *trial.charge_examples][-192:],
            coordination=[*self.coordination, *trial.coordination_examples][-512:],
            queued_fleet=[*self.queued_fleet, *trial.queue_sizes][-192:],
            aisle=[*self.aisle, *trial.aisle_examples][-512:],
            passage=[*self.passage, *trial.examples][-160:],
        )


class AttemptScore(Model):
    completed: int
    ticks: int
    finished: bool
    stalled: bool
    passage_wait: list[int] = Field(min_length=1)
    longest_wait: list[int] = Field(min_length=1)
    aisle_longest_wait: list[int] | None = None
    depleted_robots: int | None = None

    def improves(self, best: "AttemptScore") -> bool:
        if self.completed < best.completed or self.stalled > best.stalled:
            return False
        safer_energy = False
        if self.depleted_robots is not None and best.depleted_robots is not None:
            if self.depleted_robots > best.depleted_robots:
                return False
            safer_energy = self.depleted_robots < best.depleted_robots
        if best.finished and (not self.finished or self.ticks > best.ticks):
            return False
        if not self.finished and self.longest_wait[-1] > max(
            best.longest_wait[-1], NO_PROGRESS_TICK_LIMIT
        ):
            return False
        if not self.finished and self.completed == best.completed and self.ticks < best.ticks:
            return False
        # After a full completion, both models have transported the same workload.
        # At an earlier common tick, the faster model may already be in later traffic.
        horizon = min(self.ticks, best.ticks)
        time, old_time = (
            (self.ticks, best.ticks) if self.finished and best.finished else (horizon, horizon)
        )
        wait, longest = self.passage_wait[time], self.longest_wait[time]
        old_wait, old_longest = best.passage_wait[old_time], best.longest_wait[old_time]
        if wait > old_wait or longest > old_longest:
            # Fewer stranded robots can justify short additional waits, never a new jam.
            if not (
                safer_energy
                and wait <= old_wait + NO_PROGRESS_TICK_LIMIT
                and self.longest_wait[-1] <= max(best.longest_wait[-1], NO_PROGRESS_TICK_LIMIT)
            ):
                return False
        aisle_improved = False
        if self.aisle_longest_wait is not None and best.aisle_longest_wait is not None:
            aisle = self.aisle_longest_wait[time]
            old_aisle = best.aisle_longest_wait[old_time]
            if (
                self.completed == best.completed
                and self.finished == best.finished
                and aisle > old_aisle
            ):
                return False
            aisle_improved = aisle < old_aisle
        return (
            self.completed > best.completed
            or self.stalled < best.stalled
            or wait < old_wait
            or longest < old_longest
            or aisle_improved
            or safer_energy
            or (self.finished and (not best.finished or self.ticks < best.ticks))
        )


def scenario_key(scene: Scenario, *, legacy: bool = False) -> str:
    payload = scene.model_dump(mode="json")
    payload["config"]["neural_model_id"] = None
    payload["config"]["ml_model_id"] = None
    payload["config"]["control"] = "neural"
    if payload["config"]["max_ticks"] in {None, DEFAULT_MAX_TICKS}:
        del payload["config"]["max_ticks"]
    data = json.dumps(payload, sort_keys=True, separators=(",", ":"))
    # Replay weights saved before the charging reserve changed before comparing new scores.
    protocol = "v3"
    if legacy:
        protocol = "v2" if len(scene.robots) > MAX_DISPATCH_FLEET_CONTEXT else "v1"
    # Keep the storage fingerprint of previous scores after removing the run limit.
    return hashlib.sha256(f"{protocol}:4000:{data}".encode()).hexdigest()


class BestPolicy:
    def __init__(
        self, policy: NeuralPolicy, score: AttemptScore, memory: TrainingMemory | None = None
    ):
        self.policy = policy
        self.score = score
        self.memory = memory if memory is not None else TrainingMemory()


def load_best(repository: Repository, key: str) -> BestPolicy | None:
    row = repository.get(RECORD_KIND, key)
    if row is None:
        return None
    return BestPolicy(
        NeuralPolicy(row["model"]),
        AttemptScore.model_validate(row["score"]),
        TrainingMemory.model_validate(row.get("memory", {})),
    )


def consider(
    repository: Repository,
    key: str,
    policy: NeuralPolicy,
    score: AttemptScore,
    trial: "TrainingTrial | None" = None,
) -> tuple[BestPolicy, bool]:
    with promotion_lock:
        best = load_best(repository, key)
        memory = best.memory if best else TrainingMemory()
        retained = memory.record(trial) if trial is not None else memory
        promoted = best is None or score.improves(best.score)
        if best is not None and not promoted:
            if (
                best.policy.id == policy.id
                and best.score.depleted_robots is None
                and score.depleted_robots is not None
                and best.score.model_dump(exclude={"depleted_robots"})
                == score.model_dump(exclude={"depleted_robots"})
            ):
                best = BestPolicy(policy, score, retained)
            elif retained is memory:
                return best, False
            else:
                best = BestPolicy(best.policy, best.score, retained)
        else:
            best = BestPolicy(policy, score, retained)
        repository.save(
            RECORD_KIND,
            key,
            {
                "model": best.policy.artifact,
                "score": best.score.model_dump(mode="json"),
                "memory": best.memory.model_dump(mode="json"),
            },
        )
        return best, promoted


class TrainingTrial:
    """Observe a frozen run and collect alternatives to unproductive waits."""

    def __init__(self, model: NeuralPolicy, scene: Scenario):
        self.model = model
        self.id = model.id
        self.charging_weights = model.charging_weights
        self.coordination_weights = model.coordination_weights
        self.zone = narrow_passage_cells(scene.warehouse)
        self.positions = {robot.id: robot.position for robot in scene.robots}
        self.ranked: dict[Point, list[tuple[float, Action]]] = {}
        self.waiting: dict[str, int] = {}
        self.aisle_waiting: dict[str, int] = {}
        self.waits = [0]
        self.longest = [0]
        self.aisle_longest = [0]
        self.examples: deque[Preference] = deque(maxlen=128)
        self.aisle_examples: deque[tuple[int, float]] = deque(maxlen=512)
        self.coordination_examples: deque[float] = deque(maxlen=512)
        self.queue_sizes: deque[int] = deque(maxlen=128)
        self.motion_samples: deque[Experience] = deque(maxlen=192)
        self.dispatch_samples: deque[Experience] = deque(maxlen=96)
        self.charge_options: dict[Point, dict[Point, ChargingFeatures]] = {}
        self.charge_trips: dict[str, ChargingFeatures] = {}
        self.charge_examples: deque[ChargingExample] = deque(maxlen=128)
        self.depleted: set[str] = set()
        self.crossings = 0
        self.middle = scene.warehouse.width // 2
        self.sides = {rid: self.side(p) for rid, p in self.positions.items()}

    def scores(self, actions: Sequence[Action]) -> list[float]:
        scores = self.model.scores(actions)
        if actions and actions[0].kind != "move":
            options: dict[Point, ChargingFeatures] = {}
            for action in actions:
                if action.charging is not None:
                    options[action.target] = action.charging
                if action.kind == "idle" and options:
                    self.charge_options[action.target] = options
                    options = {}
        if actions and (
            actions[0].narrow_passage
            or (actions[0].wait_streak >= MIN_WAIT_AGE and actions[0].wait_streak % 8 == 0)
            or actions[0].stalled_ticks >= 8
        ):
            self.ranked[actions[0].target] = sorted(
                zip(scores, actions, strict=True), key=lambda pair: -pair[0]
            )
        return scores

    def side(self, position: Point) -> int:
        return (position[0] > self.middle) - (position[0] < self.middle - 1)

    def record_experience(self, samples: Sequence[Experience]) -> None:
        motion = [sample for sample in samples if sample.values[MOTION_FEATURE]]
        # Retain movement over more of the attempt, including each outcome class.
        for outcome in (True, False):
            group = [s for s in motion if (s.reward > 0) == outcome]
            if group:
                self.motion_samples.extend(group[:: max(1, (len(group) + 3) // 4)])
        self.dispatch_samples.extend(s for s in samples if not s.values[MOTION_FEATURE])

    def observe(self, state: SimulationState) -> None:
        self.observe_charging(state)
        waited = [decision for decision in state.neural_decisions if decision.action == "wait"]
        self.waiting = {
            d.robot_id: self.waiting.get(d.robot_id, 0) + 1 for d in waited if d.target in self.zone
        }
        self.aisle_waiting = {
            d.robot_id: self.aisle_waiting.get(d.robot_id, 0) + 1
            for d in waited
            if d.target not in self.zone
        }
        if state.tick % 16 == 0 and state.metrics.completed_tasks * 2 >= len(state.tasks):
            queued = sum(
                streak >= 24 for streak in (*self.waiting.values(), *self.aisle_waiting.values())
            )
            if queued >= 2:
                self.queue_sizes.append(queued)
        self.waits.append(self.waits[-1] + len(self.waiting))
        self.longest.append(max(self.longest[-1], max(self.waiting.values(), default=0)))
        self.aisle_longest.append(
            max(self.aisle_longest[-1], max(self.aisle_waiting.values(), default=0))
        )
        occupied = set(self.positions.values())
        targets = {robot.id: robot.position for robot in state.robots}
        for rid, target in targets.items():
            previous = self.positions[rid]
            side = self.side(target)
            if side and self.sides[rid] and self.sides[rid] != side:
                self.crossings += 1
                if previous in self.zone:
                    self.prefer_executed_crossing(previous, target)
            if side:
                self.sides[rid] = side
            if previous == target and previous in self.ranked:
                self.observe_wait(previous, occupied)
            # Sample a free neighboring cell during prolonged waits at a doorway.
            if self.waiting.get(rid, 0) in {6, 12, 24, 48}:
                ranked = self.ranked.get(previous, [])
                wait = next((action for _, action in ranked if action.target == previous), None)
                free_move = next(
                    (action for _, action in ranked if action.target not in occupied), None
                )
                if wait and free_move:
                    self.examples.append((free_move.values, wait.values))
        self.positions = targets
        self.ranked.clear()

    def observe_charging(self, state: SimulationState) -> None:
        for decision in state.neural_decisions:
            if decision.action == "charge":
                origin = self.positions[decision.robot_id]
                option = self.charge_options.get(origin, {}).get(decision.target)
                if option is not None:
                    self.charge_trips.setdefault(decision.robot_id, option)
        self.charge_options.clear()
        for robot in state.robots:
            depleted = robot.battery + 1e-9 < state.config.move_energy and robot.mode != "CHARGE"
            if depleted:
                self.depleted.add(robot.id)
            if (robot.mode == "CHARGE" or depleted) and robot.id in self.charge_trips:
                trip = self.charge_trips.pop(robot.id)
                used = max(0.0, trip.battery - robot.battery)
                self.charge_examples.append((trip.travel_energy, used, depleted))

    def observe_wait(self, origin: Point, occupied: set[Point]) -> None:
        ranked = self.ranked.get(origin, [])
        wait = next(((value, act) for value, act in ranked if act.target == origin), None)
        free = next((value for value, act in ranked if act.target not in occupied), None)
        if wait is None or free is None:
            return
        value, action = wait
        if action.stalled_ticks >= 8 and not action.coordinating:
            self.coordination_examples.append(max(0.0, value - free))
        if action.narrow_passage or action.wait_streak < MIN_WAIT_AGE or action.wait_streak % 8:
            return
        if self.model.waiting_weights is not None:
            age, penalty = self.model.waiting_weights
            if action.wait_streak >= age:
                value += penalty
        self.aisle_examples.append((action.wait_streak, max(0.0, value - free)))

    def prefer_executed_crossing(self, previous: Point, target: Point) -> None:
        ranked = self.ranked.get(previous, [])
        wait = next((action for _, action in ranked if action.target == previous), None)
        move = next((action for _, action in ranked if action.target == target), None)
        if wait and move:
            self.examples.append((move.values, wait.values))

    def score(self, state: SimulationState, stalled: bool) -> AttemptScore:
        return AttemptScore(
            completed=state.metrics.completed_tasks,
            ticks=state.tick,
            finished=state.status == "COMPLETED",
            stalled=stalled and bool(self.waiting),
            passage_wait=self.waits,
            longest_wait=self.longest,
            aisle_longest_wait=self.aisle_longest,
            depleted_robots=len(self.depleted),
        )


def candidate_from(
    parent: NeuralPolicy,
    samples: Sequence[Preference],
    general: Sequence[Experience],
    round_index: int,
) -> NeuralPolicy | None:
    passage_weights = parent.artifact.get("passage_weights")
    if samples:
        # Fit passage scores without changing dispatch or movement elsewhere.
        values = np.asarray(samples)
        for weights, bias in parent.layers[:-1]:
            values = np.maximum(values @ weights + bias, 0.0)
        differences = values[:, 0] - values[:, 1]
        weights = parent.layers[-1][0][:, 0]
        previous = parent.passage_weights
        residual = np.zeros_like(weights) if previous is None else previous
        margin = differences @ (weights + residual)
        importance = 1 / (1 + np.exp(np.clip(margin, -40, 40)))
        direction = (differences * importance[:, None]).mean(axis=0)
        scale = STEPS[round_index % len(STEPS)] / max(float(np.linalg.norm(direction)), 1e-8)
        passage_weights = (residual + scale * direction).tolist()
        layers = parent.artifact["layers"]
    elif general:
        layers = update(
            parent, parent, list(general), rate=(0.003, 0.006, 0.0015, 0.012)[round_index % 4]
        )
    else:
        return None
    model_id = weight_id(
        layers,
        passage_weights,
        parent.waiting_weights,
        parent.charging_weights,
        parent.coordination_weights,
    )
    if model_id == parent.id:
        return None
    artifact: dict[str, Any] = {**parent.artifact, "id": model_id, "layers": layers}
    if passage_weights is not None:
        artifact["passage_weights"] = passage_weights
    return NeuralPolicy(artifact)


def aisle_candidate_from(
    parent: NeuralPolicy, samples: Sequence[tuple[int, float]], round_index: int
) -> NeuralPolicy | None:
    """Fit the score correction from the margins of available yields during long waits."""
    threshold = WAIT_AGES[round_index % len(WAIT_AGES)]
    gaps = [gap for waited, gap in samples if waited >= threshold]
    if not gaps:
        return None
    quantile = (0.5, 0.25, 0.75)[round_index // len(WAIT_AGES) % 3]
    penalty = round(float(np.quantile(gaps, quantile)) + 0.5, 3)
    waiting_weights = (threshold, penalty)
    if waiting_weights == parent.waiting_weights:
        return None
    artifact = {**parent.artifact, "waiting_weights": waiting_weights}
    artifact["id"] = weight_id(
        artifact["layers"],
        artifact.get("passage_weights"),
        waiting_weights,
        parent.charging_weights,
        parent.coordination_weights,
    )
    return NeuralPolicy(artifact)


def charging_candidate_from(
    parent: NeuralPolicy, samples: Sequence[ChargingExample], critical: float, round_index: int
) -> NeuralPolicy | None:
    """Fit the reserve to travel overruns and test alternative charging priorities."""
    if not samples:
        return None
    overruns = [max(0.0, used - planned) + critical * failed for planned, used, failed in samples]
    quantile = (0.95, 0.75, 0.9)[round_index % 3]
    reserve = round(critical + float(np.quantile(overruns, quantile)), 2)
    if parent.charging_weights is not None:
        held, urgency, distance, retry, redirect = parent.charging_weights
        delta = min(5.0, max(1.0, abs(reserve - held) / 4))
        charging_weights: ChargingWeights = (
            (round(held + delta, 2), urgency, distance, retry, redirect),
            (round((held + reserve) / 2, 2), urgency, distance, retry, redirect),
            (held, urgency, distance, max(1, retry - 8), redirect),
            (held, urgency, distance, retry + 8, redirect),
            (held, round(urgency + 0.1, 2), distance, retry, redirect),
            (held, urgency, round(distance + 0.15, 2), retry, redirect),
            (held, urgency, distance, retry, round(redirect + 0.5, 2)),
        )[round_index % 7]
        return with_charging(parent, charging_weights)
    urgency, distance, retry, redirect_distance = (
        (0.6, 0.0, 48, 8.0),
        (0.3, 0.5, 24, 8.0),
        (0.5, 1.0, 48, 4.0),
        (1.0, 3.0, 24, 6.0),
    )[round_index // 3 % 4]
    return with_charging(parent, (reserve, urgency, distance, retry, redirect_distance))


def with_charging(parent: NeuralPolicy, charging_weights: ChargingWeights) -> NeuralPolicy | None:
    if charging_weights == parent.charging_weights:
        return None
    artifact = {**parent.artifact, "charging_weights": charging_weights}
    artifact["id"] = weight_id(
        artifact["layers"],
        artifact.get("passage_weights"),
        parent.waiting_weights,
        charging_weights,
        parent.coordination_weights,
    )
    return NeuralPolicy(artifact)


def coordination_candidate_from(
    parent: NeuralPolicy, margins: Sequence[float], round_index: int
) -> NeuralPolicy | None:
    """Fit the score needed to yield, then evaluate the resulting joint policy in a fresh run."""
    if parent.coordination_weights is not None:
        parent_profile = parent.coordination_weights
        variations = (
            parent_profile._replace(movement=max(0.0, parent_profile.movement - 2)),
            parent_profile._replace(movement=parent_profile.movement + 2),
            parent_profile._replace(revisit=max(0.0, parent_profile.revisit - 2)),
            parent_profile._replace(revisit=parent_profile.revisit + 2),
            parent_profile._replace(progress=max(0.0, parent_profile.progress - 1.5)),
            parent_profile._replace(progress=parent_profile.progress + 1.5),
            parent_profile._replace(stalled_ticks=max(1, parent_profile.stalled_ticks - 4)),
            parent_profile._replace(
                stalled_ticks=min(NO_PROGRESS_TICK_LIMIT - 1, parent_profile.stalled_ticks + 3)
            ),
            parent_profile._replace(duration=max(1, parent_profile.duration - 6)),
            parent_profile._replace(duration=parent_profile.duration + 6),
            parent_profile._replace(delivery_delay=max(0, parent_profile.delivery_delay - 16)),
            parent_profile._replace(delivery_delay=parent_profile.delivery_delay + 16),
            parent_profile._replace(cooldown=max(0, parent_profile.cooldown - 8)),
            parent_profile._replace(cooldown=parent_profile.cooldown + 8),
            parent_profile._replace(baseline=round(max(0.0, parent_profile.baseline - 0.1), 2)),
            parent_profile._replace(baseline=round(parent_profile.baseline + 0.1, 2)),
            parent_profile._replace(
                fraction_complete=round(max(0.0, parent_profile.fraction_complete - 0.08), 2)
            ),
            parent_profile._replace(
                fraction_complete=round(min(1.0, parent_profile.fraction_complete + 0.06), 2)
            ),
        )
        return with_coordination(parent, variations[round_index % len(variations)])
    if not margins:
        return None
    trigger, duration, progress, revisit, baseline, delay, cooldown, fraction, aging, release = (
        (20, 30, 9.0, 13.0, 0.65, 80, 28, 0.5, True, False),
        (20, 30, 6.0, 10.0, 0.85, 100, 18, 0.5, True, False),
        (24, 40, 5.0, 12.0, 0.85, 100, 20, 0.0, True, True),
        (22, 60, 0.0, 0.0, 1.0, 0, 0, 0.0, False, True),
        (20, 24, 0.0, 0.0, 1.0, 0, 0, 0.0, False, False),
    )[round_index % 5]
    quantile = (0.85, 0.75, 0.95)[round_index // 5 % 3]
    margin = float(np.quantile(margins, quantile))
    # A robot that yields can free several others. Fit the strength against the
    # observed individual score margins and validate the joint result in a run.
    movement = 0.0 if not (progress or revisit) and release else float(round(2.5 * margin))
    profile = CoordinationWeights(
        trigger,
        duration,
        movement,
        progress,
        revisit,
        baseline,
        delay,
        cooldown,
        fraction,
        aging,
        release,
    )
    return with_coordination(parent, profile)


def with_coordination(parent: NeuralPolicy, profile: CoordinationWeights) -> NeuralPolicy | None:
    if profile == parent.coordination_weights:
        return None
    artifact = {**parent.artifact, "coordination_weights": profile}
    artifact["id"] = weight_id(
        artifact["layers"],
        artifact.get("passage_weights"),
        parent.waiting_weights,
        parent.charging_weights,
        profile,
    )
    return NeuralPolicy(artifact)
