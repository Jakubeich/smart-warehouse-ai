# ruff: noqa: E402
"""Test crossing rewards that credit retreats and penalize persistent swaps."""

import argparse
import asyncio
import json
import runpy
from collections.abc import Sequence
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
parent = runpy.run_path(str(ROOT / "scripts/study-neural-yield.py"))
criteria = runpy.run_path(str(ROOT / "scripts/study-neural-yield-blend.py"))["accepted"]
MotionRecorder: Any = parent["MotionRecorder"]
PassageFeedback: Any = parent["PassageFeedback"]
train, save, maps, geometry_key, evaluate, compare, summarize = (
    parent[key]
    for key in ("train", "save", "maps", "geometry_key", "evaluate", "compare", "summarize")
)

from app.domain.models import Point, Scenario
from app.neural.online import Experience, OnlineLearning
from app.neural.policy import Action, NeuralPolicy
from app.persistence.database import Base, Repository


class RankedMotionRecorder(MotionRecorder):  # type: ignore[misc]
    def __init__(self, model: NeuralPolicy):
        super().__init__(model)
        self.preferred: dict[Point, Action] = {}

    def scores(self, actions: Sequence[Action]) -> list[float]:
        scores: list[float] = super().scores(actions)
        if actions[0].kind == "move":
            best = max(range(len(actions)), key=scores.__getitem__)
            self.preferred[actions[0].target] = actions[best]
        return scores


class FocusedPassageFeedback(PassageFeedback):  # type: ignore[misc]
    # Reward giving up space and crossing, without rewarding passive waits.
    credit_waiting = False

    def __init__(self, scene: Scenario):
        super().__init__(scene)
        self.passage_cells = set().union(*self.gates.values())
        self.previous_swaps: set[tuple[Point, Point]] = set()

    def observe(
        self,
        tick: int,
        origins: dict[str, Point],
        targets: dict[str, Point],
        recorder: RankedMotionRecorder,
        feedback: Any,
    ) -> None:
        super().observe(tick, origins, targets, recorder, feedback)
        standing = {point for rid, point in origins.items() if targets[rid] == point}
        swaps = set()
        for point in standing:
            action = recorder.preferred.get(point)
            if action is None or action.target not in standing or action.target <= point:
                continue
            if point not in self.passage_cells and action.target not in self.passage_cells:
                continue
            other = recorder.preferred.get(action.target)
            if other is None or other.target != point:
                continue
            pair = (point, action.target)
            swaps.add(pair)
            if pair in self.previous_swaps:
                feedback.motion.extend(
                    (Experience(action.values, -1.0), Experience(other.values, -1.0))
                )
                self.counts["persistent_swap_penalties"] += 2
        self.previous_swaps = swaps


def load(path: Path) -> Any:
    return json.loads(path.read_text())


async def study(out: Path) -> None:
    experiments = ROOT / "docs/experiments"
    earlier = experiments / "neural-yield-study"
    checkpoint = load(earlier / "before-checkpoint.json")
    plan = load(earlier / "plan.json")
    validation = [Scenario.model_validate(s) for s in plan["validation"] + plan["test"]]
    refs = [
        entry
        for file in ("yield-16-validation.json", "pairs.json")
        for entry in load(earlier / file)
    ]
    assert [entry["seed"] for entry in refs] == [scene.seed for scene in validation]
    reserved = load(earlier / "smaller-update/plan.json")["test"]
    testing = [Scenario.model_validate(s) for s in reserved]
    excluded = {geometry_key(s) for s in validation + testing}
    original = runpy.run_path(str(ROOT / "scripts/train-neural-fleet.py"))["scenes"](810000, 36)
    excluded.update(geometry_key(scene) for scene in original)
    for source in ("neural-online-study", "neural-speed-study", "neural-yield-study"):
        old = load(experiments / source / "plan.json")
        for group in ("train", "validation", "test"):
            excluded.update(geometry_key(Scenario.model_validate(s)) for s in old.get(group, []))
    old_pairs = load(experiments / "neural-fleet/pairs.json")["pairs"]
    excluded.update(geometry_key(Scenario.model_validate(p["scenario"])) for p in old_pairs)
    training = maps(32, 1250000, excluded)
    marks = (4, 8, 16, 32)
    save(
        out / "plan.json",
        {
            "checkpoints": marks,
            "starting_model": checkpoint["model"]["id"],
            "validation_seeds": [scene.seed for scene in validation],
            "train": [scene.model_dump(mode="json") for scene in training],
            "test": reserved,
            "selection": "Require a faster mean on joint successes with no aggregate regression "
            "in completions, passage stalls or long waits before running a frozen test.",
        },
    )
    runs, results = [], []
    with TemporaryDirectory(prefix="neural-focused-") as directory:
        repo = Repository(f"sqlite:///{directory}/study.db")
        Base.metadata.create_all(repo.engine)
        repo.save("neural_policy", "live", checkpoint)
        learner = OnlineLearning(repo)
        learner.restore()
        for index, scene in enumerate(training, 1):
            runs.append(
                await train(
                    scene,
                    repo,
                    learner,
                    pace=False,
                    passage_feedback=FocusedPassageFeedback(scene),
                    recorder_type=RankedMotionRecorder,
                )
            )
            if index in marks:
                save(out / "training.json", runs)
                save(out / f"checkpoint-{index}.json", repo.get("neural_policy", "live"))
                print("Training maps:", index, flush=True)
        repo.engine.dispose()
    reference = [entry["before"] for entry in refs]
    for index in marks:
        frozen = load(out / f"checkpoint-{index}.json")
        candidate = NeuralPolicy(frozen["model"])
        pairs = compare(validation, reference, candidate)
        measures = summarize(pairs)
        save(out / f"validation-{index}.json", pairs)
        results.append({"training_maps": index, "model": candidate.id, **measures})
        save(out / "validation-summary.json", results)
        print(index, criteria(measures), measures["after"], flush=True)
    eligible = [row for row in results if criteria(row)]
    if not eligible:
        save(out / "summary.json", {"selected": None, "reason": "No candidate met both goals."})
        return
    selected = min(
        eligible,
        key=lambda row: (
            row["after"]["mean_ticks_both_completed"] - row["before"]["mean_ticks_both_completed"]
        ),
    )
    candidate = load(out / f"checkpoint-{selected['training_maps']}.json")
    save(out / "candidate.json", candidate)
    print("Frozen selection:", selected["training_maps"], selected["model"], flush=True)
    before = NeuralPolicy(checkpoint["model"])
    pairs = compare(
        testing, [evaluate(scene, before) for scene in testing], NeuralPolicy(candidate["model"])
    )
    measures = summarize(pairs)
    save(out / "pairs.json", pairs)
    save(
        out / "summary.json",
        {
            "selected": selected["training_maps"],
            "model": selected["model"],
            "accepted": criteria(measures),
            **measures,
        },
    )


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=False)
    asyncio.run(study(args.output))


if __name__ == "__main__":
    main()
