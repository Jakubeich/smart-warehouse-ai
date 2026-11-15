import time
from pathlib import Path

import numpy as np
import pytest
from fastapi.testclient import TestClient
from sqlalchemy.exc import SQLAlchemyError

from app.core.demos import demo
from app.core.generator import GeneratorRequest, generate
from app.main import create_app
from app.neural.online import UPDATE_TICKS, Experience, OnlineLearning
from app.neural.policy import FEATURE_COUNT, resolve_moves
from app.persistence.database import Base, Repository


def test_neural_simulation_controls_dispatch_charging_and_movement(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    def forbidden(*args: object, **kwargs: object) -> None:
        pytest.fail("Neural control invoked a classical planner or scheduler")

    monkeypatch.setattr("app.simulation.engine.plan", forbidden)
    monkeypatch.setattr("app.simulation.engine.assign", forbidden)
    repo = Repository(f"sqlite:///{tmp_path}/neural.db")
    Base.metadata.create_all(repo.engine)
    scenario = generate(
        GeneratorRequest(
            seed=900001,
            width=20,
            height=18,
            robot_count=4,
            task_count=8,
            bottlenecks=True,
            passage_count=1,
            traffic="bidirectional",
        )
    )
    scenario.robots[0].battery = 12
    with TestClient(create_app(repo)) as client:
        info = client.get("/api/neural")
        assert info.status_code == 200
        created = client.post(
            "/api/simulations",
            json={
                "scenario": scenario.model_dump(mode="json"),
                "config": {
                    "control": "classical",
                    "planner": "cbs",
                    "scheduler": "learned",
                    "neural_model_id": "arbitrary-old-model",
                },
            },
        )
        assert created.status_code == 201, created.text
        initial = created.json()
        model = initial["config"]["neural_model_id"]
        assert initial["config"]["control"] == "neural"
        assert model == info.json()["id"]
        assert initial["neural_updates"] == 0
        endpoint = "/api/simulations/" + initial["id"]
        step = client.post(endpoint + "/step")
        assert step.status_code == 200, step.text
        first = step.json()
        assert {d["action"] for d in first["neural_decisions"]} >= {"task", "charge", "move"}
        for _ in range(UPDATE_TICKS - 1):
            current = client.post(endpoint + "/step").json()
        assert current["tick"] == UPDATE_TICKS
        assert current["neural_updates"] == 1
        assert current["neural_learned_samples"] > 0
        assert current["neural_last_model_id"] == model
        updated_model = current["config"]["neural_model_id"]
        assert updated_model != model
        subsequent = client.post(endpoint + "/step").json()
        assert subsequent["neural_last_model_id"] == updated_model
        assert subsequent["neural_decisions"]
        for _ in range(380):
            current = client.post(endpoint + "/step").json()
            if current["status"] in {"COMPLETED", "FAILED"}:
                break
        assert current["status"] == "COMPLETED", current["error"]
        assert current["metrics"]["completed_tasks"] == 8
        assert current["metrics"]["replans"] == current["metrics"]["executed_collisions"] == 0

        end = client.get("/api/neural").json()
        assert end["updates"] > 1
        reset = client.post(endpoint + "/reset").json()
        assert reset["tick"] == 0 and reset["neural_decisions"] == []
        assert reset["config"]["neural_model_id"] == end["id"]
        assert reset["neural_updates"] == end["updates"]
        client.delete(endpoint).raise_for_status()
    with TestClient(create_app(repo)) as restarted:
        assert restarted.get("/api/neural").json() == end
        new = restarted.post(
            "/api/simulations", json={"scenario": scenario.model_dump(mode="json")}
        ).json()
        assert new["config"]["neural_model_id"] == end["id"]
        assert new["neural_learned_samples"] == end["learned_samples"]


def test_failed_checkpoint_keeps_previous_weights(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    repo = Repository(f"sqlite:///{tmp_path}/retry.db")
    Base.metadata.create_all(repo.engine)
    learner = OnlineLearning(repo)
    base = learner.current()
    samples = [Experience((1.0,) + (0.0,) * (FEATURE_COUNT - 1), -1.0)]

    def failed_save(*args: object, **kwargs: object) -> None:
        raise SQLAlchemyError("temporarily unavailable")

    with monkeypatch.context() as control:
        control.setattr(repo, "save", failed_save)
        assert learner.learn(samples) is None
        assert learner.current() is base and learner.summary()["updates"] == 0
    learned = learner.learn(samples)
    assert learned and learned.id != base.id
    assert any(
        not np.array_equal(before[0], after[0])
        for before, after in zip(base.layers, learned.layers, strict=True)
    )
    assert learner.summary()["updates"] == 1
    repo.engine.dispose()


@pytest.mark.parametrize("should_complete", [True, False])
def test_repeated_training_restarts_and_stops(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, should_complete: bool
) -> None:
    monkeypatch.setattr("app.simulation.service.TRAINING_TICK_LIMIT", 2)
    monkeypatch.setattr("app.simulation.service.TRAINING_RESTART_DELAY", 0.15)
    repo = Repository(f"sqlite:///{tmp_path}/repeat.db")
    Base.metadata.create_all(repo.engine)
    scenario = demo("small")
    if should_complete:
        scenario.tasks = []

    with TestClient(create_app(repo)) as client:
        initial = (
            client.post("/api/simulations", json={"scenario": scenario.model_dump(mode="json")})
            .raise_for_status()
            .json()
        )
        endpoint = f"/api/simulations/{initial['id']}"
        client.post(endpoint + "/stop").raise_for_status()
        archived = repo.get("run", initial["id"])
        assert archived and archived["status"] == "STOPPED"
        client.post(endpoint + "/speed", json={"speed": 16}).raise_for_status()
        first = client.post(endpoint + "/training-start").raise_for_status().json()
        assert first["training_loop"]["attempt"] == 1 and first["status"] == "RUNNING"

        for _ in range(300):
            current = client.get(endpoint).raise_for_status().json()
            if current["training_loop"]["finished_attempts"] == 1:
                break
            time.sleep(0.01)
        assert current["training_loop"]["last_result"]["status"] == (
            "COMPLETED" if should_complete else "FAILED"
        )
        model_id = current["config"]["neural_model_id"]
        if not should_complete:
            assert current["training_loop"]["last_result"]["model_updates"] > 0
            assert model_id != initial["config"]["neural_model_id"]
            assert repo.get("neural_policy", "live")["model"]["id"] == model_id

        for _ in range(300):
            restarted = client.get(endpoint).raise_for_status().json()
            if restarted["training_loop"]["attempt"] == 2:
                break
            time.sleep(0.01)
        assert restarted["training_loop"]["attempt"] == 2
        assert restarted["sequence"] > current["sequence"]
        assert restarted["speed"] == 16 and restarted["id"] == initial["id"]
        assert model_id in {
            restarted["config"]["neural_model_id"],
            restarted["neural_last_model_id"],
        }

        stopped = client.post(endpoint + "/training-stop").raise_for_status().json()
        assert stopped["training_loop"]["active"] is False
        time.sleep(0.3)
        latest = client.get(endpoint).raise_for_status().json()
        assert latest["training_loop"]["attempt"] == stopped["training_loop"]["attempt"]
        assert latest["tick"] == stopped["tick"]
        assert repo.get("run", initial["id"]) == archived


def test_collision_filter_uses_next_ranked_neural_actions() -> None:
    original = {"a": (0, 0), "b": (1, 0), "c": (2, 1)}
    ranked = {
        "a": [(5, (1, 0)), (4, (0, 1)), (0, (0, 0))],
        "b": [(5, (0, 0)), (4, (1, 1)), (0, (1, 0))],
        "c": [(5, (1, 1)), (4, (2, 2)), (0, (2, 1))],
    }
    selected, rejected = resolve_moves(original, ranked)
    assert selected == {"a": (0, 1), "b": (1, 0), "c": (1, 1)}
    assert rejected == 3
