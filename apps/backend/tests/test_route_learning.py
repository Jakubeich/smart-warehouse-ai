import json
from collections import deque

import pytest

from app.core.generator import GeneratorRequest, generate
from app.domain.grid import Grid
from app.domain.models import Cell, Robot, Scenario, TransportTask, Warehouse
from app.learning.features import FEATURE_NAMES, LEGACY_FEATURE_NAMES, ROUTE_HORIZON, features
from app.learning.model import EtaModel
from app.scheduling.assignment import feasible
from app.simulation.engine import Engine


def test_route_distances_handle_row_boundaries_and_blocked_cells():
    warehouse = Warehouse(id="rows", name="Rows", width=4, height=4)
    grid = Grid(warehouse, {(x, 2) for x in range(4)})
    goal = (0, 1)
    assert grid.distance((1, 1), goal) == 1
    assert grid.distance((3, 0), goal) == 4
    assert grid.distance((0, 3), goal) is None
    assert grid.distance((2, 1), goal) == 2
    assert grid.shortest_path((3, 0), goal) == [(3, 0), (3, 1), (2, 1), (1, 1), goal]


@pytest.mark.parametrize("width,count", [(1, 1), (1, 2), (2, 2), (3, 3)])
def test_partition_only_crosses_at_passages_with_two_way_tasks(width, count):
    request = GeneratorRequest(
        seed=203,
        width=24,
        height=20,
        bottlenecks=True,
        passage_width=width,
        passage_count=count,
        traffic="bidirectional",
        robot_count=8,
        task_count=20,
    )
    scene = generate(request)
    assert scene == generate(request)
    grid = Grid(scene.warehouse)
    openings = json.loads(scene.warehouse.metadata["passage_rows"])
    assert len(openings) == width * count
    for x in (11, 12):
        assert [y for y in range(20) if grid.walkable((x, y))] == openings
    assert sum(t.pickup[0] > t.dropoff[0] for t in scene.tasks) == 10
    assert all(any(feasible(r, t, grid, scene.config) for r in scene.robots) for t in scene.tasks)
    reached, queue = {scene.robots[0].position}, deque([scene.robots[0].position])
    while queue:
        for p in grid.neighbors(queue.popleft()):
            if p not in reached:
                reached.add(p)
                queue.append(p)
    assert len(reached) == grid.width * grid.height - len(grid.blocked)
    assert all(grid.kind(r.home) == "CHARGER" for r in scene.robots)


def test_impossible_passage_sizes_are_rejected():
    with pytest.raises(ValueError, match="nevejdou"):
        generate(GeneratorRequest(height=10, bottlenecks=True, passage_count=3, passage_width=3))


def test_route_features_observe_current_occupancy_and_published_plans_only():
    scene = Scenario(
        id="route",
        name="Route",
        warehouse=Warehouse(
            id="route",
            name="Route",
            width=16,
            height=12,
            cells=[
                Cell(x=6, y=5, type="PICKUP"),
                Cell(x=10, y=5, type="DROPOFF"),
                Cell(x=2, y=5, type="CHARGER"),
                Cell(x=5, y=5, type="CHARGER"),
            ],
        ),
        robots=[
            Robot(id="R1", name="R1", position=(2, 5), home=(2, 5)),
            Robot(id="R2", name="R2", position=(5, 5), home=(5, 5)),
        ],
        tasks=[TransportTask(id="T1", pickup=(6, 5), dropoff=(10, 5))],
    )
    engine = Engine(scene, "route")
    a, b = engine.state.robots
    task = engine.state.tasks[0]
    b.mode = "RETURN"
    b.path = [(5, 5), (4, 5), (3, 5), (2, 5)]
    values = features(engine.state, a, task, engine.grid)
    named = dict(zip(FEATURE_NAMES, values))
    assert named["pickup_route_occupied"] == 1
    assert named["route_head_on_conflicts"] == 1
    assert named["route_opposing_edges"] == 3
    assert named["route_reserved_overlap"] == 4
    task.completed_tick = 999
    assert features(engine.state, a, task, engine.grid) == values
    b.path += [(2, 5)] * ROUTE_HORIZON + [(3, 5), (4, 5)]
    assert features(engine.state, a, task, engine.grid) == values
    b.position = (5, 7)
    b.path = [(5, 7)]
    off_route = dict(zip(FEATURE_NAMES, features(engine.state, a, task, engine.grid)))
    assert off_route["pickup_route_occupied"] == 0
    assert off_route["route_head_on_conflicts"] == 0
    assert off_route["route_opposing_edges"] == 0


def test_shortest_route_respects_obstacles_and_matches_distance():
    scene = generate(GeneratorRequest(bottlenecks=True, seed=919))
    grid = Grid(scene.warehouse)
    task = scene.tasks[0]
    route = grid.shortest_path(task.pickup, task.dropoff)
    assert len(route) - 1 == grid.distance(task.pickup, task.dropoff)
    assert all(grid.walkable(p) for p in route)
    assert all(abs(a[0] - b[0]) + abs(a[1] - b[1]) == 1 for a, b in zip(route, route[1:]))
    grid.blocked.add(task.dropoff)
    assert grid.shortest_path(task.pickup, task.dropoff) == []


def test_legacy_inference_and_feature_version_guards():
    artifact = {
        "id": "legacy-test",
        "feature_version": 1,
        "features": LEGACY_FEATURE_NAMES,
        "trees": [{"left": [-1], "right": [-1], "feature": [-2], "threshold": [-2], "value": [2]}],
    }
    values = [3.0] * len(FEATURE_NAMES)
    assert EtaModel(artifact).predict(values) == 11
    assert EtaModel(artifact).predict(values[:16]) == 11
    with pytest.raises(ValueError, match="nekompatibilní"):
        EtaModel({**artifact, "feature_version": 99})
