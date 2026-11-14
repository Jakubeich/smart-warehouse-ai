import pytest
from pydantic import ValidationError

from app.core.demos import demo
from app.domain.models import Robot, Scenario, TaskStatus
from app.scheduling.assignment import energy_needed, feasible
from app.simulation.engine import Engine
from app.simulation.invariants import InvariantError, validate_state, validate_transition


def test_scene_validation() -> None:
    s = demo()
    s.robots[1].position = s.robots[0].position
    with pytest.raises(ValidationError):
        Scenario.model_validate(s.model_dump())
    with pytest.raises(ValidationError):
        Robot(id="r", name="r", position=(0, 0), battery=101)


def test_transition_invariants() -> None:
    e = Engine(demo(), "test")
    with pytest.raises(InvariantError, match="Vertex"):
        validate_transition(e.grid, {"a": (0, 0), "b": (1, 0)}, {"a": (1, 0), "b": (1, 0)})
    with pytest.raises(InvariantError, match="swap"):
        validate_transition(e.grid, {"a": (0, 0), "b": (1, 0)}, {"a": (1, 0), "b": (0, 0)})
    with pytest.raises(InvariantError, match="movement"):
        validate_transition(e.grid, {"a": (0, 0)}, {"a": (4, 3)})


def test_energy_feasibility() -> None:
    e = Engine(demo(), "test")
    r, t = e.state.robots[0], e.state.tasks[0]
    assert energy_needed(r, t, e.grid, e.state.config) > 15
    r.battery = 1
    assert not feasible(r, t, e.grid, e.state.config)
    r.battery = 100
    r.capacity = 1
    assert not feasible(r, t, e.grid, e.state.config)


def run(seed: int) -> Engine:
    e = Engine(demo(seed=seed), "test")
    for _ in range(1000):
        previous = {r.id: r.position for r in e.state.robots}
        e.step()
        validate_transition(e.grid, previous, {r.id: r.position for r in e.state.robots})
        validate_state(e.state)
        if e.state.status in {"COMPLETED", "FAILED"}:
            break
    return e


def test_full_scenario_deterministic_and_collision_free() -> None:
    a, b = run(42), run(42)
    assert a.state.status == "COMPLETED", a.state.error
    assert a.state.tick == b.state.tick
    assert [r.model_dump() for r in a.state.robots] == [r.model_dump() for r in b.state.robots]
    assert all(t.status == TaskStatus.COMPLETED for t in a.state.tasks)
    assert a.state.metrics.executed_collisions == 0


def test_dynamic_obstacle_invalidates_paths() -> None:
    e = Engine(demo(task_count=2), "test")
    e.step()
    with pytest.raises(ValueError):
        e.obstacle(e.state.robots[0].position)
    e.obstacle((10, 1))
    assert all(len(r.path) == 1 for r in e.state.robots)
    e.step()
    assert e.state.status != "FAILED", e.state.error
    assert (10, 1) not in [r.position for r in e.state.robots]
    e.obstacle((10, 1), remove=True)
    assert e.state.obstacles == []


@pytest.mark.parametrize("seed", range(5))
def test_seeded_invariants(seed: int) -> None:
    engine = run(seed)
    assert engine.state.status == "COMPLETED", engine.state.error


def test_charging_recovers_low_battery_and_completes() -> None:
    s = demo(robot_count=1, task_count=1)
    s.robots[0].battery = 2
    e = Engine(s, "charging")
    e.step()
    assert e.state.robots[0].mode == "CHARGE"
    for _ in range(200):
        e.step()
        if e.state.status in {"COMPLETED", "FAILED"}:
            break
    assert e.state.status == "COMPLETED", e.state.error


def test_stationary_robots_do_not_move_for_cbs() -> None:
    s = demo(task_count=1)
    s.config.planner = "cbs"
    e = Engine(s, "fixed")
    offline = e.state.robots[-1]
    origin = offline.position
    e.set_available(offline.id, False)
    for _ in range(80):
        e.step()
        assert offline.position == origin
        if e.state.status in {"COMPLETED", "FAILED"}:
            break
    assert e.state.status == "COMPLETED"
