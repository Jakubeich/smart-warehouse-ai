import time
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from starlette.websockets import WebSocketDisconnect

from app.main import create_app
from app.persistence.database import Base, Repository


def test_rest_websocket_and_persistence(tmp_path: Path) -> None:
    repo = Repository(f"sqlite:///{tmp_path}/test.db")
    Base.metadata.create_all(repo.engine)
    with TestClient(create_app(repo)) as client:
        assert client.get("/api/health").status_code == 200
        assert client.get("/api/dashboard").json()["scenarios"] == []
        scenes = client.post("/api/demos").json()
        assert len(scenes) == 3
        scene = next(s for s in scenes if s["id"] == "demo-small")
        scene["tasks"] = scene["tasks"][:1]
        response = client.post("/api/simulations", json={"scenario": scene})
        assert response.status_code == 201, response.text
        sid = response.json()["id"]
        with client.websocket_connect(f"/ws/simulations/{sid}") as ws:
            initial = ws.receive_json()
            stepped = client.post(f"/api/simulations/{sid}/step").json()
            message = ws.receive_json()
            assert stepped["tick"] == 1
            assert message["sequence"] > initial["sequence"]
            assert message["state"]["tick"] == 1
        # Disconnect does not kill the simulation.
        for _ in range(100):
            state = client.post(f"/api/simulations/{sid}/step").json()
            if state["status"] == "COMPLETED":
                break
        assert state["status"] == "COMPLETED", state
        assert client.get("/api/runs").json()[0]["metrics"]["completed_tasks"] == 1
        task = dict(scene["tasks"][0], id="new-task")
        response = client.post(f"/api/simulations/{sid}/tasks", json=task)
        assert response.status_code == 201
        assert response.json()["status"] == "PAUSED"
        sequence = response.json()["sequence"]
        reset = client.post(f"/api/simulations/{sid}/reset").json()
        assert reset["tick"] == 0 and reset["sequence"] > sequence
        assert client.post(f"/api/simulations/{sid}/speed", json={"speed": -1}).status_code == 422
        assert client.get("/api/simulations/missing").status_code == 404
        assert (
            client.post(
                f"/api/simulations/{sid}/obstacles",
                json={"position": scene["robots"][0]["position"]},
            ).status_code
            == 422
        )
        saved = client.post("/api/scenarios", json=scene)
        assert saved.status_code == 201
        assert repo.get("scenario", scene["id"]) is not None


def test_delete_saved_scenario_preserves_its_live_and_archived_runs(tmp_path: Path) -> None:
    repo = Repository(f"sqlite:///{tmp_path}/test.db")
    Base.metadata.create_all(repo.engine)
    with TestClient(create_app(repo)) as client:
        scenes = client.post("/api/demos").json()
        scene = next(s for s in scenes if s["id"] == "demo-small")
        saved_id = "importovaný/sklad #1"
        client.post("/api/scenarios", json={**scene, "id": saved_id}).raise_for_status()
        request = {"scenario_id": saved_id}
        opened = client.post("/api/simulations", json=request)
        assert opened.status_code == 201
        run_id = opened.json()["id"]
        client.post(f"/api/simulations/{run_id}/stop").raise_for_status()

        assert client.delete("/api/scenarios", params=request).status_code == 204
        assert client.delete("/api/scenarios", params=request).status_code == 204
        assert client.post("/api/simulations", json=request).status_code == 404
        assert saved_id not in {s["id"] for s in client.get("/api/scenarios").json()}
        assert saved_id not in {s["id"] for s in client.get("/api/dashboard").json()["scenarios"]}
        assert client.get("/api/scenarios/demo-small").status_code == 200
        assert client.get(f"/api/simulations/{run_id}").json()["scenario_id"] == saved_id
        assert run_id in {run["id"] for run in client.get("/api/runs").json()}


def test_replace_simulation_with_stale_id_and_at_capacity(tmp_path: Path) -> None:
    repo = Repository(f"sqlite:///{tmp_path}/test.db")
    Base.metadata.create_all(repo.engine)
    with TestClient(create_app(repo)) as client:
        client.post("/api/demos").raise_for_status()
        body = {"scenario_id": "demo-small"}
        stale_id = "missing-after-restart"
        assert client.delete(f"/api/simulations/{stale_id}").status_code == 204
        with client.websocket_connect(f"/ws/simulations/{stale_id}") as ws:
            with pytest.raises(WebSocketDisconnect) as closed:
                ws.receive_json()
            assert closed.value.code == 4404

        old = client.post("/api/simulations", json={**body, "replace_id": stale_id})
        assert old.status_code == 201, old.text
        old_id = old.json()["id"]
        for _ in range(7):
            client.post("/api/simulations", json=body).raise_for_status()
        assert client.post("/api/simulations", json=body).status_code == 409

        invalid = client.post(
            "/api/simulations", json={"scenario_id": "missing", "replace_id": old_id}
        )
        assert invalid.status_code == 404
        assert client.get(f"/api/simulations/{old_id}").status_code == 200

        with client.websocket_connect(f"/ws/simulations/{old_id}") as ws:
            assert ws.receive_json()["state"]["id"] == old_id
            new = client.post("/api/simulations", json={**body, "replace_id": old_id})
            assert new.status_code == 201, new.text
            with pytest.raises(WebSocketDisconnect) as closed:
                ws.receive_json()
            assert closed.value.code == 4404

        assert client.get(f"/api/simulations/{old_id}").status_code == 404
        assert len(client.get("/api/simulations").json()) == 8
        new_id = new.json()["id"]
        stepped = client.post(f"/api/simulations/{new_id}/step").json()
        assert stepped["id"] == new_id and stepped["tick"] == 1


def test_experiment_runs_real_process_and_exports(tmp_path: Path) -> None:
    repo = Repository(f"sqlite:///{tmp_path}/test.db")
    Base.metadata.create_all(repo.engine)
    with TestClient(create_app(repo)) as client:
        client.post("/api/demos")
        response = client.post(
            "/api/experiments",
            json={"algorithms": ["astar", "cbs"], "repetitions": 1, "robot_counts": [2]},
        )
        assert response.status_code == 202, response.text
        eid = response.json()["id"]
        for _ in range(100):
            job = client.get(f"/api/experiments/{eid}").json()
            if job["status"] != "RUNNING":
                break
            time.sleep(0.05)
        assert job["status"] == "COMPLETED", job
        assert len(job["results"]) == 2
        assert all(r["source"] == "measured" for r in job["results"])
        assert all(r["metrics"]["planning_time_ms"] > 0 for r in job["results"])
        csv = client.get(f"/api/experiments/{eid}/results?format=csv")
        assert "text/csv" in csv.headers["content-type"] and "algorithm" in csv.text
        assert repo.get("experiment", eid)["status"] == "COMPLETED"


def test_database_failure_preserves_final_snapshot(tmp_path: Path, monkeypatch) -> None:
    import asyncio

    from sqlalchemy.exc import OperationalError

    from app.core.demos import demo
    from app.neural.online import OnlineLearning
    from app.simulation.service import SimulationSession

    repo = Repository(f"sqlite:///{tmp_path}/test.db")
    Base.metadata.create_all(repo.engine)
    session = SimulationSession(demo(task_count=0), repo, OnlineLearning(repo))
    session.engine.step()
    original_save = repo.save

    def unavailable(*args, **kwargs):
        raise OperationalError("save", {}, Exception("database disconnected"))

    monkeypatch.setattr(repo, "save", unavailable)
    payload = asyncio.run(session.publish())
    assert session.engine.state.status == "COMPLETED"
    assert payload["type"] == "STATE_SNAPSHOT"
    assert session.persistence_warning and not session.persisted
    monkeypatch.setattr(repo, "save", original_save)
    asyncio.run(session.publish())
    assert session.persisted and not session.persistence_warning
