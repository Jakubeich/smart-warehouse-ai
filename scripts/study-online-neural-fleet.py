# ruff: noqa: E402
"""Train the live neural controller in isolation, then test two frozen checkpoints."""

import argparse
import asyncio
import hashlib
import json
import sys
from collections import Counter
from pathlib import Path
from statistics import mean
from tempfile import TemporaryDirectory
from typing import Any, Literal

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "apps/backend"))

from app.core.generator import GeneratorRequest, generate, layout_key
from app.domain.models import CellType, Point, Scenario
from app.neural.online import OnlineLearning
from app.neural.policy import MODEL_PATH, NeuralPolicy
from app.persistence.database import Base, Repository
from app.simulation.engine import Engine
from app.simulation.service import SimulationSession

TRAIN_MAPS = 96
TEST_MAPS = 60
TICK_LIMIT = 1600
TERMINAL = {"COMPLETED", "FAILED", "STOPPED"}


def save(path: Path, data: Any) -> None:
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n")
    temporary.replace(path)


def geometry_key(scene: Scenario) -> str:
    warehouse = scene.warehouse
    walls = sorted(
        (cell.x, cell.y)
        for cell in warehouse.cells
        if cell.type in {CellType.WALL, CellType.SHELF, CellType.OBSTACLE}
    )
    return hashlib.sha256(
        json.dumps([warehouse.width, warehouse.height, walls]).encode()
    ).hexdigest()


def scenarios(
    offset: int,
    count: int,
    *,
    testing: bool,
    seen: set[str],
    geometries: set[str],
) -> list[Scenario]:
    layouts: tuple[Literal["mixed", "aisles", "islands"], ...] = ("mixed", "aisles", "islands")
    result: list[Scenario] = []
    seed = offset
    while len(result) < count:
        i = len(result)
        # Test mix: 40 one-cell scenarios, 10 wider, 10 open. Train mix: 72/12/12.
        kind = i % (6 if testing else 8)
        narrow = kind < (4 if testing else 6)
        opened = kind == (5 if testing else 7)
        fleet = (4, 6, 8, 12)[(i // 3 + i) % 4]
        scene = generate(
            GeneratorRequest(
                name=f"{'Test' if testing else 'Učení'} / {seed}",
                seed=seed,
                width=(16, 20, 24)[(i // 4 + i) % 3],
                height=(14, 18, 22)[(i // 3) % 3],
                density=(0.14, 0.24, 0.32)[(i // 5) % 3],
                layout=layouts[i % 3],
                task_count=(16, 20, 24)[(i // 2) % 3],
                robot_count=fleet,
                traffic="bidirectional",
                bottlenecks=not opened,
                passage_count=1 + (i // 4) % 2,
                passage_width=1 if narrow or opened else 2,
            )
        )
        seed += 1
        key, geometry = layout_key(scene.warehouse), geometry_key(scene)
        if key in seen or geometry in geometries:
            continue
        seen.add(key)
        geometries.add(geometry)
        if i % 4 == 0:
            scene.robots[0].battery = 12
        result.append(scene)
    return result


def passage_zone(scene: Scenario) -> set[Point]:
    options = GeneratorRequest.model_validate_json(scene.warehouse.metadata["generator"])
    if not options.bottlenecks or options.passage_width != 1:
        return set()
    wall_x = options.width // 2
    walls = {(c.x, c.y) for c in scene.warehouse.cells if c.type == CellType.WALL}
    # Include entrances as well as the two cells in the central wall.
    return {
        (xx, yy)
        for y in range(options.height)
        if (wall_x, y) not in walls
        for xx in range(wall_x - 2, wall_x + 2)
        for yy in range(max(0, y - 1), min(options.height, y + 2))
    }


class PassageWait:
    """Count uninterrupted waiting of travelling robots in passage cells/entrances."""

    def __init__(self, scene: Scenario):
        self.zone = passage_zone(scene)
        self.wait: Counter[str] = Counter()
        self.long_waits = 0
        self.longest = 0
        self.wait_ticks = 0

    def observe(self, engine: Engine) -> None:
        waited = {
            decision.robot_id
            for decision in engine.state.neural_decisions
            if decision.action == "wait" and decision.target in self.zone
        }
        self.wait_ticks += len(waited)
        for robot_id in set(self.wait) | waited:
            if robot_id not in waited:
                del self.wait[robot_id]
                continue
            self.wait[robot_id] += 1
            if self.wait[robot_id] == 10:
                self.long_waits += 1
            self.longest = max(self.longest, self.wait[robot_id])


def result(engine: Engine, waits: PassageWait) -> dict[str, Any]:
    state = engine.state
    status = state.status if state.status in TERMINAL else "TICK_LIMIT"
    stalled = status == "FAILED" and engine.stalled_ticks >= 30
    assert state.config.control == "neural" and state.metrics.replans == 0
    assert state.metrics.executed_collisions == 0
    return {
        "status": status,
        "reason": state.error,
        "ticks": state.tick,
        "completed_tasks": state.metrics.completed_tasks,
        "executed_collisions": state.metrics.executed_collisions,
        "rejected_moves": state.neural_rejections,
        "stall": stalled,
        "stall_in_passage_zone": stalled and bool(waits.wait),
        "passage_wait_ticks": waits.wait_ticks,
        "passage_waits_ge_10": waits.long_waits,
        "longest_passage_wait": waits.longest,
    }


def evaluate(scene: Scenario, policy: NeuralPolicy) -> dict[str, Any]:
    config = scene.model_copy(deep=True)
    config.config.control = "neural"
    engine = Engine(config, f"frozen-{scene.seed}", policy=policy)
    waits = PassageWait(scene)
    for _ in range(TICK_LIMIT):
        engine.step()
        waits.observe(engine)
        if engine.state.status in TERMINAL:
            break
    assert engine.policy is policy and engine.experience is None
    return result(engine, waits)


async def train(scene: Scenario, repo: Repository, learner: OnlineLearning) -> dict[str, Any]:
    session = SimulationSession(scene, repo, online=learner)
    engine = session.engine
    waits = PassageWait(scene)
    for _ in range(TICK_LIMIT):
        engine.step()
        waits.observe(engine)
        terminal = engine.state.status in TERMINAL
        await session.learn(flush=terminal)
        if terminal:
            break
    await session.learn(flush=True)
    assert not session.retry_samples
    return {"seed": scene.seed, **result(engine, waits), **learner.summary()}


def statistics(pairs: list[dict[str, Any]]) -> dict[str, Any]:
    both = [p for p in pairs if p["before"]["status"] == p["after"]["status"] == "COMPLETED"]
    data: dict[str, Any] = {"maps": len(pairs), "both_completed": len(both)}
    for model in ("before", "after"):
        runs = [p[model] for p in pairs]
        completed = sum(r["status"] == "COMPLETED" for r in runs)
        data[model] = {
            "completed": completed,
            "statuses": dict(Counter(r["status"] for r in runs)),
            "stalls": sum(r["stall"] for r in runs),
            "stalls_in_passage_zone": sum(r["stall_in_passage_zone"] for r in runs),
            "scenarios_with_passage_wait_ge_10": sum(r["passage_waits_ge_10"] > 0 for r in runs),
            "passage_waits_ge_10": sum(r["passage_waits_ge_10"] for r in runs),
            "mean_ticks_both_completed": mean(p[model]["ticks"] for p in both) if both else None,
            "mean_passage_wait_ticks_both_completed": (
                mean(p[model]["passage_wait_ticks"] for p in both) if both else None
            ),
            "executed_collisions": sum(r["executed_collisions"] for r in runs),
        }
    data["only_after_complete"] = [
        p["seed"]
        for p in pairs
        if p["before"]["status"] != "COMPLETED" and p["after"]["status"] == "COMPLETED"
    ]
    data["only_before_complete"] = [
        p["seed"]
        for p in pairs
        if p["before"]["status"] == "COMPLETED" and p["after"]["status"] != "COMPLETED"
    ]
    return data


async def study(out: Path, checkpoint: dict[str, Any] | None) -> None:
    with TemporaryDirectory(prefix="neural-study-") as workdir:
        repo = Repository(f"sqlite:///{workdir}/study.db")
        Base.metadata.create_all(repo.engine)
        learner = OnlineLearning(repo)
        if checkpoint is not None:
            if checkpoint["initial_model_id"] != learner.seed.id:
                raise ValueError("Checkpoint belongs to different initial weights")
            repo.save("neural_policy", "live", checkpoint)
            learner.restore()
        before = learner.current()
        prior_file = ROOT / "docs/experiments/neural-fleet/pairs.json"
        known = set(before.training["layout_keys"])
        geometries: set[str] = set()
        if prior_file.exists():
            for pair in json.loads(prior_file.read_text())["pairs"]:
                known.add(pair["layout"])
                geometries.add(geometry_key(Scenario.model_validate(pair["scenario"])))
        training = scenarios(1010000, TRAIN_MAPS, testing=False, seen=known, geometries=geometries)
        testing = scenarios(1020000, TEST_MAPS, testing=True, seen=known, geometries=geometries)
        sources = [
            ROOT / "apps/backend/app" / file
            for file in (
                "neural/online.py",
                "neural/policy.py",
                "simulation/engine.py",
                "simulation/service.py",
                "core/generator.py",
            )
        ] + [Path(__file__).resolve()]
        plan: dict[str, Any] = {
            "initial": learner.summary(),
            "ticks_limit": TICK_LIMIT,
            "sources": {
                str(p.relative_to(ROOT)): hashlib.sha256(p.read_bytes()).hexdigest()
                for p in sources
            },
            "train": [scene.model_dump(mode="json") for scene in training],
            "test": [scene.model_dump(mode="json") for scene in testing],
        }
        save(out / "plan.json", plan)
        save(
            out / "before-model.json",
            checkpoint["model"] if checkpoint else json.loads(MODEL_PATH.read_text()),
        )
        progress = []
        for index, scene in enumerate(training, start=1):
            run = await train(scene, repo, learner)
            progress.append(run)
            save(out / "training.json", progress)
            if index % 8 == 0 or index == len(training):
                print(
                    f"Train {index}/{len(training)} · {run['updates']} updates · {run['learned_samples']} examples",
                    flush=True,
                )
        after = learner.current()
        after_checkpoint = repo.get("neural_policy", "live")
        assert after.id != before.id and after_checkpoint is not None
        save(out / "after-checkpoint.json", after_checkpoint)
        frozen_summary = learner.summary()
        pairs = []
        for index, scene in enumerate(testing, start=1):
            settings = GeneratorRequest.model_validate_json(scene.warehouse.metadata["generator"])
            group = (
                ("narrow" if settings.passage_width == 1 else "wide")
                if settings.bottlenecks
                else "open"
            )
            first, second = evaluate(scene, before), evaluate(scene, after)
            pairs.append(
                {
                    "seed": scene.seed,
                    "layout": layout_key(scene.warehouse),
                    "group": group,
                    "robots": len(scene.robots),
                    "passages": settings.passage_count if settings.bottlenecks else 0,
                    "before": first,
                    "after": second,
                }
            )
            save(out / "pairs.json", pairs)
            if index % 10 == 0 or index == len(testing):
                print(f"Test {index}/{len(testing)}", flush=True)
        assert frozen_summary == learner.summary()
        assert after_checkpoint == repo.get("neural_policy", "live")
        assert all(
            hashlib.sha256((ROOT / p).read_bytes()).hexdigest() == h
            for p, h in plan["sources"].items()
        )
        summary = {
            "before": plan["initial"],
            "after": frozen_summary,
            "training_statuses": dict(Counter(r["status"] for r in progress)),
            "training_completed_tasks": sum(r["completed_tasks"] for r in progress),
            "all": statistics(pairs),
            "groups": {
                group: statistics([p for p in pairs if p["group"] == group])
                for group in ("narrow", "wide", "open")
            },
        }
        save(out / "summary.json", summary)
        print(json.dumps(summary, ensure_ascii=False), flush=True)
        repo.engine.dispose()


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--start-checkpoint", type=Path)
    args = parser.parse_args()
    out = args.output.resolve()
    out.mkdir(parents=True, exist_ok=False)
    checkpoint = json.loads(args.start_checkpoint.read_text()) if args.start_checkpoint else None
    asyncio.run(study(out, checkpoint))


if __name__ == "__main__":
    main()
