"""Fit and validate a reusable fleet policy on separate sets of simulated warehouses."""

import argparse
import json
import random
from collections.abc import Sequence
from concurrent.futures import ProcessPoolExecutor
from dataclasses import dataclass
from datetime import UTC, datetime
from statistics import fmean
from typing import Any, Literal, NamedTuple

from sqlalchemy import update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.generator import GeneratorRequest, generate, layout_key
from app.domain.models import NO_PROGRESS_TICK_LIMIT, Model, Scenario
from app.neural.coordination import CoordinationWeights, QueueTrigger
from app.neural.online import (
    SHARED_TRAINING_KEY as RECORD_KEY,
)
from app.neural.online import (
    SHARED_TRAINING_KIND as RECORD_KIND,
)
from app.neural.online import (
    UPDATE_TICKS,
    ExperienceBuffer,
    OnlineLearning,
)
from app.neural.policy import NeuralPolicy
from app.neural.training import (
    TrainingMemory,
    TrainingTrial,
    aisle_candidate_from,
    candidate_from,
    charging_candidate_from,
    coordination_candidate_from,
    with_coordination,
)
from app.persistence.database import Document, Repository
from app.simulation.engine import Engine


class Layout(NamedTuple):
    width: int
    height: int
    robots: int
    tasks: int
    obstacles: float
    passages: int
    passage_width: int
    low_battery: bool = False


LAYOUTS = (
    Layout(20, 16, 4, 32, 0.22, 0, 1),
    Layout(24, 18, 8, 56, 0.32, 1, 1),
    Layout(28, 22, 10, 78, 0.36, 2, 1),
    Layout(30, 20, 8, 68, 0.33, 1, 2),
    Layout(36, 28, 13, 96, 0.38, 3, 3, True),
    Layout(44, 32, 15, 140, 0.40, 1, 1),
)
PATTERNS: tuple[Literal["islands", "mixed", "aisles"], ...] = ("islands", "mixed", "aisles")


def generated_batch(
    seed: int, excluded: set[str], *, vary: bool = False, large: bool = False
) -> list[Scenario]:
    """Generate one geometry per layout, skipping any already in the other cohort."""
    scenarios = []
    for i, layout in enumerate(LAYOUTS):
        mode = PATTERNS[i % len(PATTERNS)]
        if large and i == len(LAYOUTS) - 1:
            layout = Layout(60, 60, 32, 184, 0.38, 2, 1)
        if vary:
            rng = random.Random(seed + i)
            mode = rng.choice(PATTERNS)
            layout = layout._replace(
                width=layout.width + rng.randrange(-2, 5),
                height=layout.height + rng.randrange(-2, 5),
                robots=32
                if large and i == len(LAYOUTS) - 1
                else layout.robots + rng.randrange(-1, 3),
                tasks=layout.tasks + rng.randrange(-8, 17),
                obstacles=min(0.4, layout.obstacles + rng.uniform(-0.1, 0.03)),
            )
        for retry in range(100):
            scenario = generate(
                GeneratorRequest(
                    width=layout.width,
                    height=layout.height,
                    robot_count=layout.robots,
                    task_count=layout.tasks,
                    density=layout.obstacles,
                    layout=mode,
                    bottlenecks=bool(layout.passages),
                    passage_count=max(1, layout.passages),
                    passage_width=layout.passage_width,
                    traffic="bidirectional" if layout.passages else "one_way",
                    seed=(seed + i + retry * len(LAYOUTS)) % 2**32,
                )
            )
            key = layout_key(scenario.warehouse)
            if key not in excluded:
                break
        else:
            raise RuntimeError("Could not generate a distinct validation geometry")
        excluded.add(key)
        if layout.low_battery:
            for robot in scenario.robots[::2]:
                robot.battery = 80
        scenarios.append(scenario)
    return scenarios


class MapResult(Model):
    seed: int
    layout: str
    tasks: int
    delivered: int
    finished: bool
    ticks: int
    collisions: int
    depleted: int
    passage_wait: int
    longest_passage_wait: int


@dataclass(frozen=True)
class Rollout:
    result: MapResult
    memory: TrainingMemory | None


def simulate(
    artifact: dict[str, Any],
    scene: Scenario,
    learn: bool = False,
) -> Rollout:
    policy = NeuralPolicy(artifact)
    scene = scene.model_copy(deep=True)
    scene.config.control = "neural"
    experience = ExperienceBuffer() if learn else None
    trial = TrainingTrial(policy, scene)
    engine = Engine(scene, "shared-training", policy=trial, experience=experience)
    state = engine.state
    while state.status not in {"COMPLETED", "FAILED", "STOPPED"}:
        before = state.tick
        engine.step()
        if state.tick == before:
            continue
        trial.observe(state)
        if experience is not None and state.tick % UPDATE_TICKS == 0:
            trial.record_experience(experience.drain())
    if experience is not None:
        trial.record_experience(experience.drain())
    layout = layout_key(scene.warehouse)
    memory = TrainingMemory().record(trial) if learn else None
    if memory is not None:
        memory.source_layout = layout
    return Rollout(
        MapResult(
            seed=scene.seed,
            layout=layout,
            tasks=len(scene.tasks),
            delivered=state.metrics.completed_tasks,
            finished=state.status == "COMPLETED",
            ticks=state.tick,
            collisions=state.metrics.executed_collisions,
            depleted=len(trial.depleted),
            passage_wait=trial.waits[-1],
            longest_passage_wait=trial.longest[-1],
        ),
        memory,
    )


def rank(results: Sequence[MapResult]) -> tuple[int, float, float, float]:
    finished = [result for result in results if result.finished]
    return (
        len(finished),
        fmean(result.delivered / result.tasks for result in results),
        -fmean(result.ticks / result.tasks for result in finished) if finished else 0.0,
        -fmean(result.passage_wait / result.tasks for result in results),
    )


def protects(candidate: Sequence[MapResult], incumbent: Sequence[MapResult]) -> bool:
    return len(candidate) == len(incumbent) and all(
        new.layout == old.layout
        and new.tasks == old.tasks
        and new.collisions == 0
        and new.depleted <= old.depleted
        and new.delivered >= old.delivered
        and (new.finished or not old.finished)
        and (
            not old.finished
            or new.longest_passage_wait <= max(NO_PROGRESS_TICK_LIMIT, old.longest_passage_wait)
        )
        for new, old in zip(candidate, incumbent)
    )


def proposals(
    parent: NeuralPolicy,
    memories: Sequence[TrainingMemory],
    round_index: int,
) -> list[NeuralPolicy]:
    # Every map can contribute the same number of examples to each loss.
    experiences = [x for memory in memories for x in (*memory.motion[-48:], *memory.dispatch[-24:])]
    passages = [x for memory in memories for x in memory.passage[-24:]]
    charges = [x for memory in memories for x in memory.charging[-24:]]
    margins = [x for memory in memories for x in memory.coordination[-48:]]
    queues = [x for memory in memories for x in memory.queued_fleet[-24:]]
    aisles = [x for memory in memories for x in memory.aisle[-48:]]
    motion = candidate_from(parent, [], experiences, round_index)
    charging = charging_candidate_from(parent, charges, 15.0, round_index)
    coordination = coordination_candidate_from(motion or parent, margins, round_index + 2)
    traffic_parent = coordination or motion or parent
    weights = traffic_parent.coordination_weights
    traffic = None
    if weights is not None and (queues or margins):
        threshold = (2, 3, 4)[round_index % 3]
        wait = (12, 8, 18)[round_index // 3 % 3]
        traffic = with_coordination(
            traffic_parent,
            weights._replace(
                queue_trigger=QueueTrigger(threshold, wait, 0.0, wait),
                fraction_complete=0.0,
                delivery_delay=0,
            ),
        )
    # Screen a proactive recovery profile alongside learned score updates. It can
    # intervene during an ongoing delivery rather than waiting for a global stall.
    proactive = None
    if margins or queues:
        waited = (12, 8, 18)[round_index % 3]
        proactive = with_coordination(
            parent,
            CoordinationWeights(
                20,
                24,
                12.0,
                6.0,
                9.0,
                0.75,
                0,
                10,
                0.0,
                True,
                True,
                QueueTrigger(2, waited, 0.0, waited),
            ),
        )
    candidates = (
        motion,
        charging,
        coordination,
        traffic,
        proactive,
        candidate_from(parent, passages, [], round_index),
        aisle_candidate_from(parent, aisles, round_index),
    )
    return list(
        {model.id: model for model in candidates if model and model.id != parent.id}.values()
    )


def load_shared(repository: Repository) -> dict[str, Any] | None:
    return repository.get(RECORD_KIND, RECORD_KEY)


def shared_policy(repository: Repository) -> NeuralPolicy | None:
    record = load_shared(repository)
    return NeuralPolicy(record["model"]) if record and record.get("model") else None


def shared_summary(repository: Repository) -> dict[str, Any] | None:
    record = load_shared(repository)
    if record is None:
        return None
    verification = record.get("verification")
    accepted = None
    if verification:
        results = verification["validated"][verification["accepted"]]
        accepted = {
            "maps": len(results),
            "finished": sum(result["finished"] for result in results),
            "baseline_finished": sum(
                result["finished"] for result in verification["validation_baseline"]
            ),
        }
    return {
        "id": record.get("model", {}).get("id"),
        "round": record["round"],
        "last_accepted": record["latest"]["accepted"] is not None,
        "verification": accepted,
    }


def save_round(repository: Repository, previous_round: int, payload: dict[str, Any]) -> bool:
    """Publish only if another training worker has not already advanced this round."""
    timestamp = datetime.now(UTC)
    try:
        with Session(repository.engine) as session, session.begin():
            if previous_round == 0:
                session.add(
                    Document(kind=RECORD_KIND, id=RECORD_KEY, payload=payload, updated_at=timestamp)
                )
                return True
            saved = session.execute(
                update(Document)
                .where(
                    Document.kind == RECORD_KIND,
                    Document.id == RECORD_KEY,
                    Document.payload["round"].as_integer() == previous_round,
                )
                .values(payload=payload, updated_at=timestamp)
                .returning(Document.id)
            )
            return saved.scalar_one_or_none() is not None
    except IntegrityError:
        if previous_round != 0 or load_shared(repository) is None:
            raise
        return False


def check_batch(
    pool: ProcessPoolExecutor,
    policy: NeuralPolicy,
    scenes: Sequence[Scenario],
    *,
    learn: bool = False,
) -> list[Rollout]:
    jobs = [pool.submit(simulate, policy.artifact, scene, learn) for scene in scenes]
    return [job.result() for job in jobs]


def train_round(
    pool: ProcessPoolExecutor,
    parent: NeuralPolicy,
    index: int,
    replay: Sequence[TrainingMemory] = (),
) -> tuple[NeuralPolicy | None, dict[str, Any], list[TrainingMemory]]:
    excluded: set[str] = set()
    batch_span = len(LAYOUTS) * 100
    seed = 826_100 + index * batch_span * 2
    varied = {"vary": index > 0, "large": index % 4 == 3}
    training = generated_batch(seed, excluded, **varied)
    validation = generated_batch(seed + batch_span, excluded, **varied)
    examples = check_batch(pool, parent, training, learn=True)
    samples = [entry.memory for entry in examples if entry.memory is not None]
    before = [entry.result for entry in examples]
    jobs = [
        (
            candidate,
            [pool.submit(simulate, candidate.artifact, scene) for scene in training],
        )
        for candidate in proposals(parent, [*replay, *samples], index)
    ]
    screened = [(model, [task.result().result for task in tasks]) for model, tasks in jobs]
    ranked = sorted(
        ((model, data) for model, data in screened if protects(data, before)),
        key=lambda entry: rank(entry[1]),
        reverse=True,
    )
    validation_before = [entry.result for entry in check_batch(pool, parent, validation)]
    winner = None
    winning_results = validation_before
    validated = []
    for model, data in ranked[:2]:
        if rank(data) < rank(before):
            continue
        results = [entry.result for entry in check_batch(pool, model, validation)]
        validated.append((model, results))
        if protects(results, validation_before) and rank(results) > rank(winning_results):
            winner, winning_results = model, results

    def serialize(data: Sequence[MapResult]) -> list[dict[str, Any]]:
        return [result.model_dump(mode="json") for result in data]

    report = {
        "round": index + 1,
        "baseline": parent.id,
        "accepted": winner.id if winner else None,
        "maps_in_replay": len(replay),
        "training_baseline": serialize(before),
        "validation_baseline": serialize(validation_before),
        "screened": {policy.id: serialize(results) for policy, results in screened},
        "validated": {policy.id: serialize(results) for policy, results in validated},
    }
    for memory in samples:
        # Keep a small spread of examples per map so later rounds revisit earlier layouts.
        memory.motion = memory.motion[::4][-12:]
        memory.dispatch = memory.dispatch[::4][-8:]
        memory.passage = memory.passage[::4][-6:]
        memory.charging = memory.charging[::4][-8:]
        memory.coordination = memory.coordination[::8][-12:]
        memory.queued_fleet = memory.queued_fleet[::4][-6:]
        memory.aisle = memory.aisle[::8][-12:]
    return winner, report, [*replay, *samples][-2 * len(LAYOUTS) :]


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--rounds", type=int, default=1)
    parser.add_argument("--continuous", action="store_true")
    parser.add_argument("--workers", type=int, default=4)
    parser.add_argument("--dry-run", action="store_true", help="Print results without publishing")
    args = parser.parse_args()
    if args.rounds < 1 or args.workers < 1:
        parser.error("rounds and workers must be positive")
    repository = Repository()
    online = OnlineLearning(repository)
    online.restore()
    record = load_shared(repository) or {}
    previous_round = int(record.get("round", 0))
    start = record.get("model") or record.get("seed_model")
    parent = NeuralPolicy(start) if start else online.current()
    record.setdefault("seed_model", parent.artifact)
    replay = [TrainingMemory.model_validate(raw) for raw in record.get("replay", [])]
    index = previous_round
    with ProcessPoolExecutor(max_workers=args.workers) as pool:
        while args.continuous or index < previous_round + args.rounds:
            winner, report, replay = train_round(pool, parent, index, replay=replay)
            print(json.dumps(report), flush=True)
            index += 1
            if winner:
                parent = winner
                record.update(model=winner.artifact, verification=report)
            record.update(
                round=index,
                latest=report,
                replay=[m.model_dump(mode="json") for m in replay],
                live_experience=[
                    {
                        "layout": memory.source_layout,
                        "samples": [
                            {"values": sample.values, "reward": sample.reward}
                            for sample in (*memory.motion, *memory.dispatch)
                        ],
                    }
                    for memory in replay[-len(LAYOUTS) :]
                    if memory.source_layout is not None
                ],
            )
            if not args.dry_run and not save_round(repository, index - 1, record):
                parser.exit(1, "Another training process has already published this round.\n")


if __name__ == "__main__":
    main()
