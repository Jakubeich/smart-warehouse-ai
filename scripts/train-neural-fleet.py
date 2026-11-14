# ruff: noqa: E402
"""Train a shared MLP to rank warehouse control actions from expert demonstrations."""

import argparse
import hashlib
import json
import os
import sys
from collections import Counter, deque
from pathlib import Path
from typing import Literal

os.environ.setdefault("OPENBLAS_NUM_THREADS", "1")
os.environ.setdefault("OMP_NUM_THREADS", "1")
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "apps/backend"))

import numpy as np
from sklearn.neural_network import MLPClassifier

from app.core.demos import demo
from app.core.generator import GeneratorRequest, generate, layout_key
from app.domain.grid import Grid
from app.domain.models import Point, Robot, Scenario, TaskStatus
from app.neural.policy import (
    FEATURE_VERSION,
    MODEL_PATH,
    Action,
    NeuralPolicy,
    dispatch_actions,
    motion_actions,
)
from app.simulation.engine import Engine


class Demonstrations(Engine):
    def __init__(self, scene: Scenario):
        super().__init__(scene, f"teacher-{scene.seed}")
        self.rows: list[tuple[float, ...]] = []
        self.labels: list[int] = []
        self.chosen: Counter[str] = Counter()
        self.open_grid = self.grid
        self.recent: dict[str, deque[Point]] = {r.id: deque(maxlen=12) for r in scene.robots}

    def record(self, actions: list[Action], selected: Action) -> None:
        self.chosen[selected.kind] += 1
        for action in actions:
            self.rows.append(action.values)
            self.labels.append(int(action is selected))

    def _dispatch(self) -> None:
        s = self.state
        available = sorted((r for r in s.robots if r.mode == "IDLE"), key=lambda r: r.id)
        positions = {r.position for r in s.robots}
        pending = [t for t in s.tasks if t.status == TaskStatus.PENDING]
        stations = {
            p
            for t in s.tasks
            if t.status in {TaskStatus.ASSIGNED, TaskStatus.IN_PROGRESS}
            for p in (t.pickup, t.dropoff)
        }
        goals = {r.goal for r in s.robots if r.goal is not None}
        # Sample the same choices the neural controller sees before the teacher moves.
        for r in available:
            actions = dispatch_actions(
                s, self.grid, r, pending, stations, goals, positions - {r.position}
            )
            self.record(actions, self.dispatch_expert(r, actions))
        super()._dispatch()
        if not self.dirty:
            self.record_moves()

    def dispatch_expert(self, robot: Robot, actions: list[Action]) -> Action:
        # Demonstrate charging and parking decisions too. Charge before accepting
        # work when low, and otherwise favor priority, age, and short pickup legs.
        charge = [a for a in actions if a.kind == "charge"]
        jobs = [a for a in actions if a.task is not None]
        if charge and (
            robot.battery < self.state.config.critical_threshold
            or (not jobs and robot.battery < robot.battery_capacity)
        ):
            return min(charge, key=lambda a: (a.target != robot.home, a.values[11]))
        if jobs:
            return max(jobs, key=lambda a: a.values[13] + 0.25 * a.values[14] - 0.22 * a.values[11])
        parking = next((a for a in actions if a.kind == "park"), None)
        return parking or actions[-1]

    def record_moves(self) -> None:
        s = self.state
        fixed = {
            r.position for r in s.robots if r.goal in {None, r.position} or r.service_remaining
        }
        if self.open_grid.blocked != self.grid.blocked | fixed:
            self.open_grid = Grid(s.warehouse, set(s.obstacles) | fixed)
        occupants = {r.position: r for r in s.robots}
        for robot in s.robots:
            actions = motion_actions(
                s, self.grid, self.open_grid, robot, occupants, self.recent[robot.id]
            )
            self.recent[robot.id].append(robot.position)
            chosen = robot.path[min(robot.path_index + 1, len(robot.path) - 1)]
            selected = next((a for a in actions if a.target == chosen), None)
            if selected is not None:
                self.record(actions, selected)

    def _plan(self) -> bool:
        success = super()._plan()
        if success:
            self.record_moves()
        return success


def collect(scene: Scenario) -> Demonstrations:
    engine = Demonstrations(scene)
    for _ in range(1400):
        engine.step()
        if engine.state.status in {"COMPLETED", "FAILED"}:
            break
    return engine


def scenes(offset: int, count: int) -> list[Scenario]:
    result = []
    layouts: tuple[Literal["aisles", "islands", "mixed"], ...] = ("aisles", "islands", "mixed")
    for i in range(count):
        seed = offset + i
        fleet = [3, 4, 6, 8, 12][i % 5]
        scene = generate(
            GeneratorRequest(
                seed=seed,
                width=[16, 20, 24][i % 3],
                height=[14, 18, 22][(i // 3) % 3],
                robot_count=fleet,
                task_count=16 + i % 3 * 4,
                density=[0.12, 0.22, 0.32][(i // 3) % 3],
                layout=layouts[(i // 3) % 3],
                traffic="bidirectional",
                bottlenecks=i % 4 != 0,
                passage_count=1 + (i // 4) % 2,
                passage_width=1 + (i // 8) % 2,
            )
        )
        if i % 5 == 0:
            scene.robots[0].battery = 12
        result.append(scene)
    result.extend(
        demo(size, offset + count + i) for i, size in enumerate(("small", "medium", "large"))
    )
    return result


def main() -> None:
    args = argparse.ArgumentParser(description=__doc__)
    args.add_argument("--maps", type=int, default=36)
    args.add_argument("--epochs", type=int, default=32)
    opt = args.parse_args()
    rng = np.random.default_rng(742)
    rows: list[np.ndarray] = []
    labels: list[np.ndarray] = []
    counts: Counter[str] = Counter()
    status: Counter[str] = Counter()
    layouts = set()
    for i, scene in enumerate(scenes(810000, opt.maps)):
        example = collect(scene)
        x, y = np.asarray(example.rows, dtype=np.float32), np.asarray(example.labels)
        if len(y) > 9000:
            indices = rng.choice(len(y), 9000, replace=False)
            x, y = x[indices], y[indices]
        rows.append(x)
        labels.append(y)
        counts.update(example.chosen)
        status[example.state.status] += 1
        layouts.add(layout_key(scene.warehouse))
        if i % 10 == 0:
            print(f"Collected {i + 1}: {example.state.status}, {len(y)} candidate rows", flush=True)
    x, y = np.concatenate(rows), np.concatenate(labels)
    print(f"Fitting on {len(y)} rows", flush=True)
    # Rebalance motion and dispatch so that repetitive idle decisions do not dominate.
    weight = np.ones(len(y), dtype=np.float32)
    for index in range(5):
        subset = x[:, index] == 1
        for label in (0, 1):
            group = subset & (y == label)
            if group.any():
                weight[group] = len(y) / (10 * group.sum())
    network = MLPClassifier(
        hidden_layer_sizes=(48, 32),
        random_state=742,
        max_iter=opt.epochs,
        batch_size=512,
        learning_rate_init=0.002,
        verbose=True,
    )
    network.fit(x, y, sample_weight=weight)
    layers = [
        {"weights": w.astype(float).tolist(), "bias": b.astype(float).tolist()}
        for w, b in zip(network.coefs_, network.intercepts_, strict=True)
    ]
    digest = hashlib.sha256(json.dumps(layers, separators=(",", ":")).encode()).hexdigest()
    artifact = {
        "id": f"nn-{digest[:12]}",
        "feature_version": FEATURE_VERSION,
        "layers": layers,
        "training": {
            "seed": 742,
            "generator_seed": 810000,
            "maps": opt.maps + 3,
            "rows": len(y),
            "demonstrations_before_sampling": counts,
            "status": status,
            "layout_keys": sorted(layouts),
            "epochs": network.n_iter_,
        },
    }
    model = NeuralPolicy(artifact)
    probe = x[:: max(1, len(x) // 100)]
    logits = model.scores([Action("move", (0, 0), tuple(row)) for row in probe.tolist()])
    assert np.allclose(
        1 / (1 + np.exp(-np.asarray(logits))), network.predict_proba(probe)[:, 1], atol=1e-5
    )
    temp = MODEL_PATH.with_suffix(".tmp")
    temp.write_text(json.dumps(artifact, separators=(",", ":")) + "\n")
    temp.replace(MODEL_PATH)
    print(model.id, artifact["training"], flush=True)


if __name__ == "__main__":
    main()
