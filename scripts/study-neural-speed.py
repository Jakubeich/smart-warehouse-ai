# ruff: noqa: E402
"""Continue on-policy learning and compare frozen models on new narrow maps."""

import argparse
import asyncio
import json
import runpy
import sys
from collections import Counter
from pathlib import Path
from statistics import median
from tempfile import TemporaryDirectory
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "apps/backend"))

from app.core.generator import GeneratorRequest, generate
from app.domain.models import Scenario
from app.neural.online import Experience, ExperienceBuffer, OnlineLearning
from app.neural.policy import NeuralPolicy
from app.persistence.database import Base, Repository
from app.simulation.service import SimulationSession

helpers = runpy.run_path(str(ROOT / "scripts/study-online-neural-fleet.py"))
save, geometry_key = helpers["save"], helpers["geometry_key"]
evaluate, statistics = helpers["evaluate"], helpers["statistics"]
PassageWait, result = helpers["PassageWait"], helpers["result"]
LIMIT = helpers["TICK_LIMIT"]


class SpeedFeedback(ExperienceBuffer):
    """Reward quick pickups and discourage costly detours to charge when work is available."""

    def dispatch_finished(self, robot_id: str, tick: int) -> None:
        if entry := self.pending.pop(robot_id, None):
            values, started, optimistic_ticks = entry
            elapsed = max(1, tick - started)
            if values[
                0
            ]:  # Task: subtract loaded distance and handling, which the robot can't choose.
                pickup_and_delay = max(0.0, elapsed - 32 * values[12] - 20 * values[17])
                reward = max(-0.8, 1.4 - pickup_and_delay / 9)
            elif values[1] and values[9] and values[5] > 0.55:
                reward = -0.8  # This robot could serve work; avoid topping up a healthy battery.
            else:
                reward = min(1.0, optimistic_ticks / elapsed)
            if reward:
                self.dispatch.append(Experience(values, reward))

    def drain(self) -> list[Experience]:
        samples = super().drain()
        # Preserve conflict feedback while prioritizing the dispatch outcomes relevant to throughput.
        return samples + [sample for sample in samples if sample.values[0] or sample.values[1]] * 4


def maps(count: int, seed: int, excluded: set[str]) -> list[Scenario]:
    scenarios = []
    for index in range(count):
        fleet = (4, 6, 8, 12)[index % 4]
        while True:
            scene = generate(
                GeneratorRequest(
                    name=f"Úzký sklad {seed}",
                    width=(16, 20, 24)[(index // 4) % 3],
                    height=(14, 18, 22)[(index // 7) % 3],
                    density=(0.14, 0.24, 0.32)[(index // 4) % 3],
                    robot_count=fleet,
                    task_count=(16, 20, 24)[(index // 4) % 3],
                    seed=seed,
                    traffic="bidirectional",
                    bottlenecks=True,
                    passage_count=1 + (index // 4) % 2,
                    passage_width=1,
                )
            )
            seed += 1
            geometry = geometry_key(scene)
            if geometry not in excluded:
                excluded.add(geometry)
                break
        if (index // 4 + index) % 5 == 0:
            scene.robots[0].battery = 12
        scenarios.append(scene)
    return scenarios


async def train(
    scene: Scenario, repo: Repository, learner: OnlineLearning, *, speed: bool
) -> dict[str, Any]:
    session = SimulationSession(scene, repo, online=learner)
    engine = session.engine
    if speed:
        engine.experience = SpeedFeedback()
    waits = PassageWait(scene)
    for _ in range(LIMIT):
        engine.step()
        waits.observe(engine)
        terminal = engine.state.status in {"COMPLETED", "FAILED"}
        await session.learn(flush=terminal)
        if terminal:
            break
    await session.learn(flush=True)
    assert not session.retry_samples
    note: dict[str, Any] = result(engine, waits)
    return {"seed": scene.seed, **note}


def compare(
    scenarios: list[Scenario], reference: list[dict[str, Any]], policy: NeuralPolicy
) -> list[dict[str, Any]]:
    return [
        {
            "seed": scene.seed,
            "robots": len(scene.robots),
            "before": before,
            "after": evaluate(scene, policy),
        }
        for scene, before in zip(scenarios, reference, strict=True)
    ]


def summarize(pairs: list[dict[str, Any]]) -> dict[str, Any]:
    summary: dict[str, Any] = statistics(pairs)
    deltas = [
        p["after"]["ticks"] - p["before"]["ticks"]
        for p in pairs
        if p["before"]["status"] == p["after"]["status"] == "COMPLETED"
    ]
    summary["median_paired_ticks_delta"] = median(deltas) if deltas else None
    summary["faster_tied_slower"] = [
        sum(d < 0 for d in deltas),
        deltas.count(0),
        sum(d > 0 for d in deltas),
    ]
    return summary


async def study(out: Path, checkpoint: dict[str, Any]) -> None:
    initial = runpy.run_path(str(ROOT / "scripts/train-neural-fleet.py"))["scenes"](810000, 36)
    prior = json.loads((ROOT / "docs/experiments/neural-online-study/plan.json").read_text())
    old = json.loads((ROOT / "docs/experiments/neural-fleet/pairs.json").read_text())["pairs"]
    excluded = {geometry_key(scene) for scene in initial}
    excluded.update(
        geometry_key(Scenario.model_validate(s)) for s in prior["train"] + prior["test"]
    )
    excluded.update(geometry_key(Scenario.model_validate(p["scenario"])) for p in old)
    training = maps(96, 1110000, excluded)
    validation = maps(24, 1120000, excluded)
    testing = maps(64, 1130000, excluded)
    save(
        out / "plan.json",
        {
            "starting_model": checkpoint["model"]["id"],
            "tick_limit": LIMIT,
            "train": [s.model_dump(mode="json") for s in training],
            "validation": [s.model_dump(mode="json") for s in validation],
            "test": [s.model_dump(mode="json") for s in testing],
            "selection": (
                "On validation, prioritize zero newly unfinished runs, fewer stalls, fewer long-wait maps, "
                "and lower mean ticks on joint completions. Use only one selected model on the final test set."
            ),
        },
    )
    save(out / "before-checkpoint.json", checkpoint)
    before = NeuralPolicy(checkpoint["model"])
    val_reference = [evaluate(scene, before) for scene in validation]
    results = []
    for name in ("standard", "speed-feedback"):
        with TemporaryDirectory(prefix="neural-speed-") as directory:
            repo = Repository(f"sqlite:///{directory}/study.db")
            Base.metadata.create_all(repo.engine)
            repo.save("neural_policy", "live", checkpoint)
            learner = OnlineLearning(repo)
            learner.restore()
            runs = []
            for index, scene in enumerate(training, 1):
                runs.append(await train(scene, repo, learner, speed=name == "speed-feedback"))
                if index % 16 == 0:
                    print(
                        f"{name}: training {index}/{len(training)}, {dict(Counter(run['status'] for run in runs))}",
                        flush=True,
                    )
                if index in (32, 64, 96):
                    candidate = learner.current()
                    pairs = compare(validation, val_reference, candidate)
                    summary = summarize(pairs)
                    saved = repo.get("neural_policy", "live")
                    assert saved and saved["model"]["id"] == candidate.id
                    label = f"{name}-{index}"
                    save(out / f"{label}.json", saved)
                    save(out / f"{label}-validation.json", pairs)
                    results.append({"label": label, **summary})
                    save(out / "validation-summary.json", results)
                    print(label, summary["faster_tied_slower"], summary["after"], flush=True)
            save(out / f"{name}-training.json", runs)
            repo.engine.dispose()

    def rank(value: dict[str, Any]) -> tuple[int, int, int, int, float]:
        after, before_stats = value["after"], value["before"]
        return (
            len(value["only_before_complete"]),
            max(0, after["stalls"] - before_stats["stalls"]),
            max(
                0,
                after["scenarios_with_passage_wait_ge_10"]
                - before_stats["scenarios_with_passage_wait_ge_10"],
            ),
            -after["completed"],
            (after["mean_ticks_both_completed"] - before_stats["mean_ticks_both_completed"])
            if value["both_completed"]
            else float("inf"),
        )

    selected = min(results, key=rank)
    final = json.loads((out / f"{selected['label']}.json").read_text())
    save(out / "after-checkpoint.json", final)
    print(
        f"Frozen selection: {selected['label']}, {final['model']['id']}. Testing on untouched scenarios.",
        flush=True,
    )
    reference = [evaluate(scene, before) for scene in testing]
    pairs = compare(testing, reference, NeuralPolicy(final["model"]))
    save(out / "pairs.json", pairs)
    summary = summarize(pairs)
    save(out / "summary.json", {"selected": selected["label"], **summary})
    print(json.dumps(summary), flush=True)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--start-checkpoint", type=Path, required=True)
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=False)
    asyncio.run(study(args.output, json.loads(args.start_checkpoint.read_text())))


if __name__ == "__main__":
    main()
