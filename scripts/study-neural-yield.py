# ruff: noqa: E402
"""Credit neural actions that unblock teammates, then evaluate on unseen layouts."""

import argparse
import asyncio
import json
import runpy
from collections import Counter, deque
from collections.abc import Sequence
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
speed = runpy.run_path(str(ROOT / "scripts/study-neural-speed.py"))
maps, save, geometry_key = (speed[key] for key in ("maps", "save", "geometry_key"))
evaluate, summarize, compare = (speed[key] for key in ("evaluate", "summarize", "compare"))
PassageWait, result, LIMIT = (speed[key] for key in ("PassageWait", "result", "LIMIT"))

from app.domain.models import CellType, Point, Scenario
from app.neural.online import Experience, ExperienceBuffer, OnlineLearning
from app.neural.policy import Action, NeuralPolicy
from app.persistence.database import Base, Repository
from app.simulation.service import SimulationSession


class MotionRecorder:
    """Record the exact candidates ranked by the neural net, without altering scores."""

    def __init__(self, model: NeuralPolicy):
        self.id = model.id
        self.model = model
        self.moves: dict[Point, dict[Point, Action]] = {}

    def scores(self, actions: Sequence[Action]) -> list[float]:
        if actions[0].kind == "move":
            self.moves[actions[0].target] = {action.target: action for action in actions}
        return self.model.scores(actions)


class YieldFeedback(ExperienceBuffer):
    def __init__(self, pace: bool):
        super().__init__()
        self.pace = pace

    def dispatch_finished(self, robot_id: str, tick: int) -> None:
        if not self.pace:
            super().dispatch_finished(robot_id, tick)
            return
        if entry := self.pending.pop(robot_id, None):
            values, started, optimistic = entry
            elapsed = max(1, tick - started)
            if values[0]:  # Keep completed jobs positive; prioritize low avoidable cost.
                pickup_and_delay = max(0.0, elapsed - 32 * values[12] - 20 * values[17])
                reward = 0.35 + 1.3 / (1.0 + pickup_and_delay / 10.0)
            elif values[1]:  # Reward useful charging in proportion to the energy restored.
                reward = 0.9 * (1 - values[5]) - (0.25 if values[9] and values[5] >= 0.8 else 0)
            else:
                reward = min(0.3, optimistic / elapsed)
            if reward:
                self.dispatch.append(Experience(values, reward))


class PassageFeedback:
    credit_waiting = True

    def __init__(self, scene: Scenario):
        self.center = scene.warehouse.width // 2
        walls = {(c.x, c.y) for c in scene.warehouse.cells if c.type == CellType.WALL}
        self.gates = {
            row: {(x, row) for x in (self.center - 1, self.center)}
            for row in range(scene.warehouse.height)
            if (self.center, row) not in walls
        }
        self.entries: dict[str, int] = {}
        self.recent: deque[tuple[int, str, int, Action]] = deque()
        self.counts: Counter[str] = Counter()

    def observe(
        self,
        tick: int,
        origins: dict[str, Point],
        targets: dict[str, Point],
        recorder: MotionRecorder,
        feedback: YieldFeedback,
    ) -> None:
        while self.recent and tick - self.recent[0][0] > 8:
            self.recent.popleft()
        for rid, target in targets.items():
            origin = origins[rid]
            selected = recorder.moves.get(origin, {}).get(target)
            if selected is None:
                continue
            for row, opening in self.gates.items():
                if origin in opening and target not in opening:
                    side = -1 if target[0] < self.center else 1
                    if (entry := self.entries.pop(rid, None)) is not None and entry != side:
                        feedback.motion.append(Experience(selected.values, 0.65))
                        self.counts["crossings"] += 1
                        # Credit a teammate who waited or made room at this same entrance.
                        keep: deque[tuple[int, str, int, Action]] = deque()
                        credited = set()
                        for sample_tick, other, other_row, action in reversed(self.recent):
                            if other != rid and other_row == row:
                                if other not in credited:
                                    feedback.motion.append(Experience(action.values, 1.0))
                                    credited.add(other)
                                    self.counts["yield_rewards"] += 1
                            else:
                                keep.appendleft((sample_tick, other, other_row, action))
                        self.recent = keep
                if target in opening and origin not in opening:
                    self.entries[rid] = -1 if origin[0] < self.center else 1
                near = abs(origin[1] - row) <= 1 and self.center - 2 <= origin[0] <= self.center + 1
                if not near:
                    continue
                if (self.credit_waiting and origin == target) or selected.distance_gain < 0:
                    self.recent.append((tick, rid, row, selected))

    def penalize_stall(self, feedback: YieldFeedback) -> None:
        # An unresolved passage queue supplies negative credit to the last selected action.
        seen = set()
        for _, rid, _, action in reversed(self.recent):
            if rid not in seen:
                feedback.motion.append(Experience(action.values, -1.0))
                seen.add(rid)
                self.counts["stall_penalties"] += 1


async def train(
    scene: Scenario,
    repo: Repository,
    learner: OnlineLearning,
    *,
    pace: bool,
    passage_feedback: PassageFeedback | None = None,
    recorder_type: type[MotionRecorder] = MotionRecorder,
) -> dict[str, Any]:
    session = SimulationSession(scene, repo, online=learner)
    engine = session.engine
    feedback = YieldFeedback(pace)
    engine.experience = feedback
    passage_feedback = passage_feedback or PassageFeedback(scene)
    waits = PassageWait(scene)
    for _ in range(LIMIT):
        policy = engine.policy
        assert isinstance(policy, NeuralPolicy)
        recorder = recorder_type(policy)
        engine.policy = recorder
        origins = {r.id: r.position for r in engine.state.robots}
        engine.step()
        engine.policy = policy
        waits.observe(engine)
        passage_feedback.observe(
            engine.state.tick,
            origins,
            {r.id: r.position for r in engine.state.robots},
            recorder,
            feedback,
        )
        terminal = engine.state.status in {"COMPLETED", "FAILED"}
        if terminal and engine.stalled_ticks >= 30:
            passage_feedback.penalize_stall(feedback)
        await session.learn(flush=terminal)
        if terminal:
            break
    await session.learn(flush=True)
    assert not session.retry_samples
    return {
        "seed": scene.seed,
        **result(engine, waits),
        "feedback": dict(passage_feedback.counts),
    }


def rank(summary: dict[str, Any]) -> tuple[int, int, int, float, int]:
    before, after = summary["before"], summary["after"]
    delta = (
        after["mean_ticks_both_completed"] - before["mean_ticks_both_completed"]
        if summary["both_completed"]
        else float("inf")
    )
    return (
        max(0, before["completed"] - after["completed"]),
        max(0, after["stalls"] - before["stalls"]),
        max(
            0,
            after["scenarios_with_passage_wait_ge_10"]
            - before["scenarios_with_passage_wait_ge_10"],
        ),
        delta,
        len(summary["only_before_complete"]),
    )


async def study(out: Path, checkpoint: dict[str, Any]) -> None:
    original = runpy.run_path(str(ROOT / "scripts/train-neural-fleet.py"))["scenes"](810000, 36)
    excluded = {geometry_key(scene) for scene in original}
    experiments = ROOT / "docs/experiments"
    for source in ("neural-online-study", "neural-speed-study"):
        plan = json.loads((experiments / source / "plan.json").read_text())
        for kind in ("train", "validation", "test"):
            excluded.update(geometry_key(Scenario.model_validate(s)) for s in plan.get(kind, []))
    prior = json.loads((experiments / "neural-fleet/pairs.json").read_text())
    excluded.update(geometry_key(Scenario.model_validate(p["scenario"])) for p in prior["pairs"])
    training = maps(64, 1210000, excluded)
    validation = maps(32, 1220000, excluded)
    testing = maps(64, 1230000, excluded)
    save(
        out / "plan.json",
        {
            "tick_limit": LIMIT,
            "initial_model": checkpoint["model"]["id"],
            "train": [s.model_dump(mode="json") for s in training],
            "validation": [s.model_dump(mode="json") for s in validation],
            "test": [s.model_dump(mode="json") for s in testing],
            "selection": "First minimize regressions in completion, stalls and long waits; then mean tick delta.",
        },
    )
    save(out / "before-checkpoint.json", checkpoint)
    baseline = NeuralPolicy(checkpoint["model"])
    reference = [evaluate(scene, baseline) for scene in validation]
    results = []
    for name, pace in (("yield", False), ("yield-and-pace", True)):
        with TemporaryDirectory(prefix="neural-yield-") as directory:
            repo = Repository(f"sqlite:///{directory}/study.db")
            Base.metadata.create_all(repo.engine)
            repo.save("neural_policy", "live", checkpoint)
            learner = OnlineLearning(repo)
            learner.restore()
            runs = []
            for index, scene in enumerate(training, 1):
                runs.append(await train(scene, repo, learner, pace=pace))
                if index % 8 == 0:
                    print(
                        name,
                        "training",
                        index,
                        dict(Counter(run["status"] for run in runs)),
                        flush=True,
                    )
                if index in (8, 16, 32, 64):
                    label = f"{name}-{index}"
                    candidate = learner.current()
                    pairs = compare(validation, reference, candidate)
                    summary = summarize(pairs)
                    save(out / f"{label}.json", repo.get("neural_policy", "live"))
                    save(out / f"{label}-validation.json", pairs)
                    results.append({"label": label, **summary})
                    save(out / "validation-summary.json", results)
                    print(label, "validation", rank(summary), flush=True)
            save(out / f"{name}-training.json", runs)
            repo.engine.dispose()
    choice = min(results, key=rank)
    candidate = json.loads((out / f"{choice['label']}.json").read_text())
    save(out / "after-checkpoint.json", candidate)
    print("Frozen selection:", choice["label"], candidate["model"]["id"], flush=True)
    reference = [evaluate(scene, baseline) for scene in testing]
    pairs = compare(testing, reference, NeuralPolicy(candidate["model"]))
    save(out / "pairs.json", pairs)
    summary = {"selected": choice["label"], **summarize(pairs)}
    save(out / "summary.json", summary)
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
