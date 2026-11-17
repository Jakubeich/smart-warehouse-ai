import time
from collections import deque
from collections.abc import Sequence
from pathlib import Path

import numpy as np
import pytest
from fastapi.testclient import TestClient
from sqlalchemy.exc import SQLAlchemyError

from app.core.demos import demo
from app.core.generator import GeneratorRequest, generate
from app.domain.grid import Grid
from app.domain.models import Point, Scenario
from app.main import create_app
from app.neural.coordination import simultaneous_moves
from app.neural.online import UPDATE_TICKS, Experience, OnlineLearning
from app.neural.policy import (
    FEATURE_COUNT,
    Action,
    ChargingFeatures,
    NeuralPolicy,
    charging_score,
    dispatch_actions,
    load_policy,
    motion_actions,
    resolve_moves,
    weight_id,
)
from app.neural.shared import (
    MapResult,
    generated_batch,
    protects,
    save_round,
    simulate,
)
from app.neural.training import (
    AttemptScore,
    aisle_candidate_from,
    charging_candidate_from,
    consider,
    scenario_key,
)
from app.persistence.database import Base, Repository
from app.simulation.engine import TRAINING_STALL_MESSAGE, TRAINING_STALL_TICKS, Engine


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
    monkeypatch.setattr("app.simulation.service.TRAINING_RESTART_DELAY", 0.15)
    repo = Repository(f"sqlite:///{tmp_path}/repeat.db")
    Base.metadata.create_all(repo.engine)
    scenario = demo("small")
    if should_complete:
        scenario.tasks = scenario.tasks[:1]
    else:
        for task in scenario.tasks:
            task.payload_weight = 1000

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
        client.post(endpoint + "/speed", json={"speed": 512}).raise_for_status()
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
        outcome = current["training_loop"]["last_result"]
        assert outcome["checkpoint"] == ("saved" if should_complete else "kept")
        assert (model_id != initial["config"]["neural_model_id"]) is should_complete
        assert repo.list("neural_scenario_best") == []

        for _ in range(300):
            restarted = client.get(endpoint).raise_for_status().json()
            if restarted["training_loop"]["attempt"] == 2:
                break
            time.sleep(0.01)
        assert restarted["training_loop"]["attempt"] == 2
        assert restarted["sequence"] > current["sequence"]
        assert restarted["speed"] == 512 and restarted["id"] == initial["id"]
        candidate_id = restarted["config"]["neural_model_id"]
        if not should_complete:
            assert candidate_id == model_id

        stopped = client.post(endpoint + "/training-stop").raise_for_status().json()
        assert stopped["training_loop"]["active"] is False
        time.sleep(0.3)
        latest = client.get(endpoint).raise_for_status().json()
        assert latest["training_loop"]["attempt"] == stopped["training_loop"]["attempt"]
        assert latest["tick"] == stopped["tick"]
        assert repo.get("run", initial["id"]) == archived

    with TestClient(create_app(repo)) as client:
        restored = client.get("/api/neural").raise_for_status().json()
        normal = client.post(
            "/api/simulations", json={"scenario": scenario.model_dump(mode="json")}
        ).raise_for_status().json()
        assert normal["config"]["neural_model_id"] == restored["id"]


def test_shared_training_respects_default_and_explicit_step_limits() -> None:
    scene = demo("small", robot_count=1, task_count=23)
    scene.robots[0].battery_capacity = scene.robots[0].battery = 500
    for task in scene.tasks:
        task.load_duration = task.unload_duration = 100
    limited = simulate(load_policy().artifact, scene).result
    assert not limited.finished and limited.ticks == 4000
    assert 0 < limited.delivered < 23

    scene.config.max_ticks = 5638
    result = simulate(load_policy().artifact, scene).result
    assert result.finished and result.delivered == 23 and result.ticks == 5638


@pytest.mark.parametrize(
    ("depleted", "queued", "expected"),
    [
        (0, 1, (TRAINING_STALL_TICKS + 10, "Simulation step limit reached.")),
        (0, 3, (TRAINING_STALL_TICKS + 1, TRAINING_STALL_MESSAGE)),
        (2, 1, (TRAINING_STALL_TICKS + 1, TRAINING_STALL_MESSAGE)),
        (3, 0, (1, "Most available robots are out of energy.")),
    ],
)
def test_training_restarts_when_most_robots_cannot_progress(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    depleted: int,
    queued: int,
    expected: tuple[int, str],
) -> None:
    scene = demo("small", robot_count=4, task_count=1)
    scene.config.max_ticks = TRAINING_STALL_TICKS + 10
    for x, robot in enumerate(scene.robots, 1):
        robot.position = (x + 5, 1)
        if x <= depleted:
            robot.battery = 0

    def simulate_queue(engine: Engine) -> tuple[dict[str, Point], list[Experience]]:
        robots = engine.state.robots
        for waiting in robots[3 - queued : 3]:
            waiting.goal = (waiting.position[0], 2)
        circling = robots[-1]
        circling.goal = (9, 7)
        moves = {robot.id: robot.position for robot in engine.state.robots}
        moves[circling.id] = (9, 2 if circling.position[1] == 1 else 1)
        return moves, []

    monkeypatch.setattr(Engine, "_neural_dispatch", lambda _: None)
    monkeypatch.setattr(Engine, "_neural_moves", simulate_queue)
    monkeypatch.setattr("app.simulation.service.TRAINING_RESTART_DELAY", 0.05)
    repo = Repository(f"sqlite:///{tmp_path}/blocked.db")
    Base.metadata.create_all(repo.engine)
    with TestClient(create_app(repo)) as client:
        state = client.post(
            "/api/simulations", json={"scenario": scene.model_dump(mode="json")}
        ).raise_for_status().json()
        endpoint = f"/api/simulations/{state['id']}"
        client.post(endpoint + "/speed", json={"speed": 512}).raise_for_status()
        client.post(endpoint + "/training-start").raise_for_status()
        for _ in range(300):
            training = client.get(endpoint).raise_for_status().json()["training_loop"]
            if training["attempt"] == 2:
                break
            time.sleep(0.01)
        assert training["attempt"] == 2
        last = training["last_result"]
        assert last["status"] == "FAILED"
        assert (last["ticks"], last["error"]) == expected


@pytest.mark.parametrize("depleted", [1, 2])
def test_fleet_stops_for_a_depleted_majority(depleted: int) -> None:
    scene = demo("small", robot_count=3, task_count=1)
    scene.config.control = "neural"
    scene.config.wait_energy = 0.1
    for x, robot in enumerate(scene.robots[:depleted], 1):
        robot.position = (x, 1)
        robot.battery = 0
    engine = Engine(scene, "fleet-energy")
    if depleted == 1:
        result = simulate(load_policy().artifact, scene).result
        assert result.finished and result.delivered == 1
    else:
        state = engine.step()
        assert state.status == "FAILED" and state.error == "Most available robots are out of energy."


def test_simulation_stops_when_fleet_motion_repeats_without_a_delivery() -> None:
    class CirclingPolicy:
        id = "circling"

        def scores(self, actions: Sequence[Action]) -> list[float]:
            neighbor = (3, 1) if actions[0].target == (2, 1) else (2, 1)
            return [
                float(action.kind == "task" or (action.kind == "move" and action.target == neighbor))
                for action in actions
            ]

    scene = demo("small", robot_count=1, task_count=1)
    scene.config.control = "neural"
    scene.config.move_energy = 0
    scene.robots[0].position = (2, 1)
    engine = Engine(scene, "fleet-loop", policy=CirclingPolicy())
    for _ in range(430):
        engine.step()
        if engine.state.status == "FAILED":
            break
    assert engine.state.status == "FAILED" and engine.stalled_ticks == 0
    assert engine.state.error == "The fleet is repeating the same state without completing a delivery."


def test_training_requires_throughput_without_passage_regression() -> None:
    best = AttemptScore(
        completed=8,
        ticks=3,
        finished=False,
        stalled=True,
        passage_wait=[0, 2, 3, 5],
        longest_wait=[0, 1, 2, 2],
    )
    assert best.model_copy(update={"completed": 9}).improves(best)
    assert best.model_copy(update={"stalled": False}).improves(best)
    assert not best.model_copy(update={"completed": 9, "passage_wait": [0, 3, 4, 6]}).improves(best)
    assert not best.model_copy(update={"completed": 9, "longest_wait": [0, 1, 2, 3]}).improves(best)
    assert not best.model_copy(update={"completed": 7, "stalled": False}).improves(best)
    assert not best.model_copy(update={"ticks": 2}).improves(best)


def test_finished_attempts_compare_waiting_over_the_delivered_workload() -> None:
    incumbent = AttemptScore(
        completed=2, ticks=4, finished=True, stalled=False,
        passage_wait=[0, 0, 1, 2, 6], longest_wait=[0, 0, 1, 2, 3],
        aisle_longest_wait=[0, 0, 2, 3, 4], depleted_robots=0,
    )
    faster = incumbent.model_copy(update={
        "ticks": 3, "passage_wait": [0, 1, 3, 5], "longest_wait": [0, 1, 2, 3],
    })
    assert faster.improves(incumbent)
    assert not faster.model_copy(update={"depleted_robots": 1}).improves(incumbent)


def test_full_size_neural_fleet_accepts_work_on_generated_warehouse() -> None:
    scene = generate(
        GeneratorRequest(
            seed=3610735511,
            width=45,
            height=64,
            density=0.4,
            robot_count=32,
            task_count=200,
            bottlenecks=True,
            passage_width=2,
            passage_count=3,
            traffic="bidirectional",
        )
    )
    scene.config.control = "neural"
    engine = Engine(scene, "full-size-fleet", policy=load_policy())
    state = engine.step()

    assert any(decision.action == "task" for decision in state.neural_decisions)
    assert state.metrics.total_distance > 0
    assert state.metrics.executed_collisions == 0


def test_shared_training_uses_separate_layouts_and_protects_each_map() -> None:
    seen: set[str] = set()
    first = generated_batch(900100, seen)
    earlier = set(seen)
    second = generated_batch(900700, seen, vary=True, large=True)
    assert len(first) == len(second) == len(earlier)
    assert len(seen - earlier) == len(first)
    assert any(robot.battery < robot.battery_capacity for scene in second for robot in scene.robots)
    assert second[-1].warehouse.width >= 58 and len(second[-1].tasks) >= 176
    assert len(second[-1].robots) == 32
    old = MapResult(
        seed=900100, layout="A", tasks=8, delivered=8, finished=True, ticks=16,
        collisions=0, depleted=0, passage_wait=3, longest_passage_wait=2,
    )
    assert protects([old.model_copy(update={"ticks": 15})], [old])
    for regression in ({"delivered": 7}, {"depleted": 1}, {"collisions": 1},
                       {"layout": "B"}, {"longest_passage_wait": 31}):
        assert not protects([old.model_copy(update=regression)], [old])


def test_live_runs_share_learning_across_custom_and_generated_maps(tmp_path: Path) -> None:
    repository = Repository(f"sqlite:///{tmp_path}/shared.db")
    Base.metadata.create_all(repository.engine)
    packaged = load_policy()
    bootstrap = charging_candidate_from(packaged, [(10.0, 17.0, False)], 15.0, 0)
    assert bootstrap is not None
    custom = demo("small", robot_count=1, task_count=1)
    custom.warehouse.cells = [
        cell for cell in custom.warehouse.cells if (cell.x, cell.y) != (4, 3)
    ]
    generated = generate(GeneratorRequest(width=17, height=13, seed=9342, robot_count=2, task_count=3))
    generated.config.move_energy = 0.7
    archived_score = AttemptScore(
        completed=1, ticks=1, finished=True, stalled=False,
        passage_wait=[0, 0], longest_wait=[0, 0], depleted_robots=0,
    )
    consider(repository, scenario_key(custom), packaged, archived_score)
    row = {"round": 1, "model": bootstrap.artifact, "latest": {"accepted": bootstrap.id}}
    assert save_round(repository, 0, row)
    assert not save_round(repository, 0, row)

    def open_run(client: TestClient, scene: Scenario) -> tuple[str, str]:
        state = client.post(
            "/api/simulations", json={"scenario": scene.model_dump(mode="json")}
        ).raise_for_status().json()
        return f"/api/simulations/{state['id']}", state["config"]["neural_model_id"]

    with TestClient(create_app(repository)) as client:
        path, initial_model = open_run(client, custom)
        assert initial_model == bootstrap.id
        client.post(path + "/step").raise_for_status()
        state = client.post(path + "/pause").raise_for_status().json()
        updated_model = state["config"]["neural_model_id"]
        assert updated_model != initial_model
        assert client.get("/api/neural").raise_for_status().json()["replay_layouts"] == 1

        path, new_model = open_run(client, generated)
        assert new_model == updated_model
        from_generator = Experience((0.0,) * FEATURE_COUNT, 0.5)
        newer = {
            "round": 2, "model": packaged.artifact, "latest": {"accepted": packaged.id},
            "live_experience": [{
                "layout": "generated-by-worker",
                "samples": [{"values": from_generator.values, "reward": from_generator.reward}],
            }],
        }
        assert save_round(repository, 1, newer)
        assert not save_round(repository, 1, row)
        client.post(path + "/speed", json={"speed": 512}).raise_for_status()
        client.post(path + "/training-start").raise_for_status()
        for _ in range(250):
            attempt = client.get(path).raise_for_status().json()["training_loop"]["last_result"]
            if attempt is not None:
                break
            time.sleep(0.01)
        assert attempt and attempt["status"] == "COMPLETED" and attempt["model_updates"] > 0
        client.post(path + "/training-stop").raise_for_status()
        latest = client.get("/api/neural").raise_for_status().json()
        assert latest["id"] not in {updated_model, packaged.id}
        assert latest["replay_layouts"] == 3
        assert open_run(client, custom)[1] == latest["id"]
        record = repository.get("neural_policy", "live")
        assert record is not None and record["generated_round"] == 2
        assert record["replay"]["generated-by-worker"][0]["reward"] == 0.5
        assert NeuralPolicy(record["model"]).charging_weights == bootstrap.charging_weights

    with TestClient(create_app(repository)) as client:
        assert open_run(client, generated)[1] == latest["id"]
        assert client.get("/api/neural").raise_for_status().json()["replay_layouts"] == 3


def test_aisle_learning_fits_wait_scores_without_changing_passage_decisions() -> None:
    parent = load_policy()
    candidate = aisle_candidate_from(parent, [(120, 4.0), (140, 8.0)], 0)
    assert candidate is not None
    assert candidate.id != parent.id
    assert parent.waiting_weights is None
    candidate = NeuralPolicy(candidate.artifact)
    features = (0.0,) * FEATURE_COUNT
    threshold, penalty = candidate.waiting_weights or (0, 0.0)
    assert threshold > 0 and penalty > 0
    wait = Action("move", (3, 3), features, wait_streak=threshold)
    passage = Action("move", (3, 3), features, narrow_passage=True, wait_streak=threshold)
    earlier = Action("move", (3, 3), features, wait_streak=threshold - 1)
    assert candidate.scores([wait]) == pytest.approx([parent.scores([wait])[0] - penalty])
    assert candidate.scores([passage]) == parent.scores([passage])
    assert candidate.scores([earlier]) == parent.scores([earlier])


def test_neural_motion_accounts_for_a_robot_that_cannot_move() -> None:
    scene = demo("small")
    scene.config.control = "neural"
    engine = Engine(scene, "depleted-robot")
    stuck = engine.state.robots[0]
    stuck.goal = engine.state.robots[1].position
    stuck.mode = "RETURN"
    stuck.battery = scene.config.move_energy / 2
    new, _ = engine._neural_moves()
    assert new[stuck.id] == stuck.position
    assert engine.motion_grid is not None
    assert not engine.motion_grid.walkable(stuck.position)


def test_charging_candidate_learns_reserve_and_prefers_short_available_route() -> None:
    policy = load_policy()
    samples = [(12.0, 16.0, False), (10.0, 25.0, True)]
    candidate = charging_candidate_from(policy, samples, 15.0, 0)
    assert candidate is not None and candidate.id != policy.id
    weights = NeuralPolicy(candidate.artifact).charging_weights
    assert weights is not None and weights[0] > 15.0
    near = ChargingFeatures(48.0, 8.0, 8.0, 0.4, False, redirecting=True)
    far = ChargingFeatures(48.0, 26.0, 8.0, 0.4, False, redirecting=True)
    healthy = ChargingFeatures(100.0, 8.0, 8.0, 0.4, False)
    assert charging_score(near, weights) > charging_score(far, weights)
    weak = ChargingFeatures(25.0, 8.0, 8.0, 0.4, False)
    assert charging_score(weak, weights) > charging_score(healthy, weights)


def test_low_battery_charging_keeps_wait_and_steps_toward_the_charger() -> None:
    engine = Engine(demo("small"), "charge-reserve")
    robot = engine.state.robots[0]
    assert robot.home is not None
    robot.mode, robot.goal = "RETURN", robot.home
    robot.position = (robot.home[0] + 2, robot.home[1])
    robot.battery = 4
    visits = deque([robot.position])
    grid = engine.grid
    actions = motion_actions(
        engine.state, grid, grid, robot, {robot.position: robot}, visits, charging=True
    )
    assert {action.target for action in actions} == {robot.position, (2, robot.home[1])}

    robot.battery = robot.battery_capacity
    actions = motion_actions(
        engine.state, grid, grid, robot, {robot.position: robot}, visits, charging=True
    )
    assert (4, robot.home[1]) in {action.target for action in actions}


def test_charging_candidates_skip_unreachable_and_claimed_stations() -> None:
    scene = demo("small")
    engine = Engine(scene, "charging-options")
    robot = engine.state.robots[0]
    occupied, reserved, blocked = engine.grid.chargers[1:]
    robot.battery = 50.0
    available = dispatch_actions(
        engine.state,
        engine.grid,
        robot,
        [],
        set(),
        {reserved},
        {occupied},
        charging_grid=Grid(scene.warehouse, {blocked}),
    )
    assert [action.target for action in available if action.kind == "charge"] == [robot.position]
    robot.battery = 0.0
    available = dispatch_actions(
        engine.state,
        engine.grid,
        robot,
        [],
        set(),
        {reserved},
        {occupied},
        charging_grid=Grid(scene.warehouse, {blocked, robot.position}),
    )
    assert [action.target for action in available if action.kind == "charge"] == [robot.position]


def test_neural_driver_retargets_an_occupied_charger_before_depletion() -> None:
    scene = demo("small")
    scene.config.control = "neural"
    scene.robots = scene.robots[:2]
    base = load_policy()
    weights = (40.0, 12.0, 1.0, 12, 20.0)
    policy = NeuralPolicy(
        {
            **base.artifact,
            "charging_weights": weights,
            "id": weight_id(base.artifact["layers"], charging_weights=weights),
        }
    )
    engine = Engine(scene, "retarget-charger", policy=policy)
    robot, other = engine.state.robots
    robot.position, robot.battery = (5, 12), 7.0
    robot.mode, robot.goal = "RETURN", other.position
    engine.neural_charging.add(robot.id)
    engine.motion_waits[robot.id] = 20
    engine.set_available(other.id, False)
    engine._neural_dispatch()
    assert robot.goal == (4, 12)
    assert robot.id in engine.neural_charging
    assert {decision.action for decision in engine.state.neural_decisions} == {"charge"}


def test_checkpoint_can_trade_short_passage_wait_for_fewer_depleted_robots() -> None:
    old = AttemptScore(
        completed=10,
        ticks=2,
        finished=False,
        stalled=False,
        passage_wait=[0, 4, 8],
        longest_wait=[0, 4, 5],
        depleted_robots=2,
    )
    safer = old.model_copy(
        update={
            "completed": 11,
            "depleted_robots": 0,
            "passage_wait": [0, 6, 30],
            "longest_wait": [0, 5, 15],
        }
    )
    assert safer.improves(old)
    assert not safer.model_copy(update={"completed": 9}).improves(old)
    assert not safer.model_copy(update={"longest_wait": [0, 5, 31]}).improves(old)
    assert not safer.model_copy(update={"depleted_robots": 2}).improves(old)


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


def test_joint_neural_choice_can_clear_a_queue_without_allowing_a_swap() -> None:
    origins = {"a": (0, 0), "b": (1, 0), "parked": (0, 1)}
    ranked = {
        "a": [(9.0, (1, 0)), (0.0, (0, 0))],
        "b": [(8.0, (0, 0)), (6.0, (1, 0)), (3.0, (1, 1))],
    }
    assert resolve_moves(origins, ranked)[0] == origins
    assert simultaneous_moves(origins, ranked) == {"a": (1, 0), "b": (1, 1), "parked": (0, 1)}
