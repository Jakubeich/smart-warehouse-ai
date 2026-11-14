import asyncio
import json
import time
from collections import deque
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.core.generator import GeneratorRequest, generate, layout_key
from app.domain.grid import Grid
from app.learning.features import FEATURE_NAMES, features
from app.learning.model import EtaModel, train
from app.learning.runner import comparison_summary, run_episode
from app.learning.service import Learning
from app.main import create_app
from app.persistence.database import Base, Repository
from app.scheduling.assignment import assign, feasible
from app.simulation.engine import Engine


@pytest.fixture(scope="module")
def episodes():
    return [
        run_episode(
            generate(
                GeneratorRequest(
                    seed=600 + i, task_count=16, width=16 + (i % 3) * 4, height=12 + (i % 2) * 4
                )
            ).model_dump(mode="json"),
            ["priority", "nearest", "hungarian"][i % 3],
            "training",
        )["episode"]
        for i in range(8)
    ]


@pytest.fixture(scope="module")
def model(episodes):
    return train(episodes, seed=91)


@pytest.mark.parametrize("layout", ["aisles", "islands", "mixed"])
def test_generator_seed_and_connectivity(layout):
    a = generate(GeneratorRequest(layout=layout, seed=12, robot_count=8))
    b = generate(GeneratorRequest(layout=layout, seed=12, robot_count=8))
    c = generate(GeneratorRequest(layout=layout, seed=13, robot_count=8))
    assert a == b
    assert layout_key(a.warehouse) != layout_key(c.warehouse)
    assert {(x.x, x.y) for x in a.warehouse.cells if x.type == "SHELF"} != {
        (x.x, x.y) for x in c.warehouse.cells if x.type == "SHELF"
    }
    grid = Grid(a.warehouse)
    reached, queue = {a.robots[0].position}, deque([a.robots[0].position])
    while queue:
        for p in grid.neighbors(queue.popleft()):
            if p not in reached:
                reached.add(p)
                queue.append(p)
    assert len(reached) == grid.width * grid.height - len(grid.blocked)
    assert len({r.home for r in a.robots}) == 8
    assert all(grid.kind(r.home) == "CHARGER" for r in a.robots)
    assert all(any(feasible(r, t, grid, a.config) for r in a.robots) for t in a.tasks)


def test_observations_are_dispatch_features_and_measured_labels():
    scene = generate(GeneratorRequest(seed=51, task_count=3))
    engine = Engine(scene, "observed")
    initial = engine.state.model_copy(deep=True)
    engine.step()
    for row in engine.pending_observations.values():
        r = next(r for r in initial.robots if r.id == row["robot_id"])
        t = next(t for t in initial.tasks if t.id == row["task_id"])
        assert row["features"] == features(initial, r, t, engine.grid)
    for _ in range(1500):
        engine.step()
        if engine.state.status in {"COMPLETED", "FAILED"}:
            break
    assert engine.state.status == "COMPLETED"
    assert len(engine.observations) == 3
    for row in engine.observations:
        t = next(t for t in engine.state.tasks if t.id == row["task_id"])
        assert row["actual_ticks"] == t.completed_tick - t.assigned_tick
        assert len(row["features"]) == len(FEATURE_NAMES)
    episode = engine.learning_episode()
    assert episode["unfinished"] == 0
    assert episode["layout_key"] == layout_key(scene.warehouse)


def test_incomplete_tasks_are_not_training_labels():
    engine = Engine(generate(GeneratorRequest(task_count=2)), "incomplete")
    engine.step()
    engine.fail("Forced incomplete test run")
    assert engine.learning_episode()["unfinished"] > 0
    assert engine.learning_episode()["samples"] == []


def test_forest_fits_real_labels_and_keeps_layouts_separate(model, episodes):
    assert model["samples"] == sum(len(ep["samples"]) for ep in episodes)
    assert model["train_samples"] > 0 and model["test_samples"] > 0
    assert set(model["train_layouts"]).isdisjoint(model["test_layouts"])
    assert len(model["trees"]) == 96
    assert model["metrics"]["mae"] >= 0
    restored = EtaModel(json.loads(json.dumps(model)))
    assert restored.predict(episodes[0]["samples"][0]["features"]) > 0
    # Evaluation data never changes the fitted dataset or its fingerprint.
    other = train([*episodes, {**episodes[0], "purpose": "evaluation"}], seed=91)
    assert other["dataset_hash"] == model["dataset_hash"]
    assert other["metrics"] == model["metrics"]
    legacy = {**episodes[0], "feature_version": 1, "id": "legacy"}
    assert train([*episodes, legacy], seed=91)["dataset_hash"] == model["dataset_hash"]


def test_insufficient_training_and_missing_model_are_explicit():
    with pytest.raises(ValueError, match="60"):
        train([])
    scene = generate(GeneratorRequest())
    scene.config.scheduler = "learned"
    with pytest.raises(ValueError, match="model"):
        Engine(scene, "missing")
    with pytest.raises(ValueError, match="model"):
        assign(scene.robots, scene.tasks, Grid(scene.warehouse), scene.config)


def test_learned_scheduler_uses_predictions_and_preserves_energy_guard(model):
    scene = generate(GeneratorRequest(seed=101, task_count=6))
    scene.config.scheduler = "learned"
    scene.robots[0].battery = 1
    engine = Engine(scene, "learned", EtaModel(model))
    engine.step()
    assert engine.state.config.ml_model_id == model["id"]
    assert engine.state.assignment_decisions
    for decision in engine.state.assignment_decisions:
        best = min(decision.candidates, key=lambda c: (c.predicted_ticks, c.robot_id))
        assert best.robot_id == decision.robot_id
        assert decision.robot_id != scene.robots[0].id
    for _ in range(1200):
        engine.step()
        if engine.state.status in {"COMPLETED", "FAILED"}:
            break
    assert engine.state.status == "COMPLETED", engine.state.error
    assert engine.state.metrics.executed_collisions == 0


def test_paired_summary_excludes_unpaired_successes():
    def result(status, makespan):
        return {
            "status": status,
            "assignments": {"T": "R"},
            "metrics": dict.fromkeys(
                [
                    "makespan",
                    "average_task_completion_time",
                    "total_waiting",
                    "total_distance",
                    "planning_time_ms",
                ],
                makespan,
            ),
        }

    summary = comparison_summary(
        [
            {"baseline": result("COMPLETED", 100), "learned": result("COMPLETED", 90)},
            {"baseline": result("COMPLETED", 30), "learned": result("FAILED", 1)},
        ]
    )
    assert summary["successful_pairs"] == 1
    assert summary["baseline_successes"] == 2 and summary["learned_successes"] == 1
    assert summary["metrics"]["makespan"]["improvement_percent"] == 10


def wait_job(client, job_id):
    for _ in range(300):
        result = client.get(f"/api/learning/jobs/{job_id}").json()
        if result["status"] not in {"RUNNING", "CANCELLING"}:
            return result
        time.sleep(0.05)
    pytest.fail("Learning job did not finish")


def test_learning_api_persistence_and_comparison_isolation(tmp_path: Path, episodes):
    repo = Repository(f"sqlite:///{tmp_path}/learning.db")
    Base.metadata.create_all(repo.engine)
    for ep in episodes:
        repo.save("ml_episode", ep["id"], ep)
    with TestClient(create_app(repo)) as client:
        generated = client.post("/api/generator", json={"seed": 800}).json()
        assert generated["seed"] == 800
        job = client.post("/api/learning/jobs", json={"action": "train"})
        assert job.status_code == 202
        trained = wait_job(client, job.json()["id"])
        assert trained["status"] == "COMPLETED", trained
        mid = trained["model_id"]
        assert client.get("/api/learning").json()["active_model_id"] == mid
        before = client.get("/api/learning").json()["dataset"]
        comparison = client.post(
            "/api/learning/jobs", json={"action": "compare", "maps": 2, "seed": 8000}
        )
        compared = wait_job(client, comparison.json()["id"])
        assert compared["status"] == "COMPLETED", compared
        assert len(compared["pairs"]) == 2
        assert all(p["unseen_layout"] for p in compared["pairs"])
        assert all(p["baseline"]["seed"] == p["learned"]["seed"] for p in compared["pairs"])
        assert client.get("/api/learning").json()["dataset"] == before
        client.post("/api/scenarios", json=generated).raise_for_status()
        repeated = client.post(
            "/api/learning/jobs",
            json={"action": "compare", "scenario_id": generated["id"], "maps": 2},
        )
        assert repeated.status_code == 422
        saved_job = client.post(
            "/api/learning/jobs",
            json={"action": "compare", "scenario_id": generated["id"], "maps": 1},
        )
        saved_comparison = wait_job(client, saved_job.json()["id"])
        assert saved_comparison["status"] == "COMPLETED"
        assert saved_comparison["pairs"][0]["scenario"] == generated
        assert saved_comparison["pairs"][0]["seed"] == generated["seed"]
        assert client.get("/api/learning").json()["dataset"] == before
    # A fresh registry resolves the model using only persisted JSON after restart.
    registry = Learning(repo)
    assert registry.active_model().id == mid
    asyncio.run(registry.close())


def test_repeated_generated_episodes_do_not_duplicate_training_data():
    data = generate(GeneratorRequest(seed=88, task_count=2)).model_dump(mode="json")
    a = run_episode(data, "priority", "training")["episode"]
    b = run_episode(data, "priority", "training")["episode"]
    assert a["id"] == b["id"]
    assert a["samples"] == b["samples"]


def test_learning_concurrent_create_and_cancel(tmp_path: Path):
    from app.learning.service import LearningRequest

    repo = Repository(f"sqlite:///{tmp_path}/cancel.db")
    Base.metadata.create_all(repo.engine)
    registry = Learning(repo)

    async def exercise():
        # Pause the worker while checking admission/cancellation, without running a fake simulator.
        gate = asyncio.Event()
        original = registry.run

        async def delayed(*args):
            await gate.wait()
            await original(*args)

        registry.run = delayed
        results = await asyncio.gather(
            registry.create(LearningRequest(action="collect_train")),
            registry.create(LearningRequest(action="collect_train")),
            return_exceptions=True,
        )
        jobs = [r for r in results if isinstance(r, dict)]
        assert len(jobs) == 1
        assert sum(isinstance(r, ValueError) for r in results) == 1
        registry.cancel(jobs[0]["id"])
        gate.set()
        await asyncio.gather(*registry.tasks)
        assert repo.get("ml_job", jobs[0]["id"])["status"] == "CANCELLED"
        assert registry.overview()["active_model_id"] is None
        assert registry.overview()["dataset"]["samples"] == 0
        await registry.close()

    asyncio.run(exercise())
