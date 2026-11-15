"""Headless benchmark runners. Each run receives a fresh identical scenario per seed."""

import platform
import random
import sys
from dataclasses import asdict
from statistics import mean, pstdev
from time import perf_counter
from typing import Any

from app.algorithms.mapf import plan
from app.domain.grid import Grid
from app.domain.models import Cell, CellType, Robot, Scenario, TransportTask
from app.schemas.requests import ExperimentRequest
from app.simulation.engine import Engine


def prepare(base: Scenario, request: ExperimentRequest, seed: int, fleet: int) -> Scenario:
    scene = base.model_copy(deep=True)
    scene.seed = seed
    rng = random.Random(seed)
    if request.benchmark == "A":
        scene.warehouse.cells = [c for c in scene.warehouse.cells if c.type != CellType.SHELF]
    elif request.benchmark == "B":
        # Preserve the selected warehouse's narrow aisles.
        pass
    elif request.benchmark == "C":
        # Same map with robots concentrated in adjacent valid starting positions below.
        pass
    grid = Grid(scene.warehouse)
    starts = [r.position for r in scene.robots]
    spare = [
        (x, y)
        for y in range(scene.warehouse.height - 1, -1, -1)
        for x in range(scene.warehouse.width)
        if grid.walkable((x, y))
        and grid.kind((x, y)) in {CellType.FLOOR, CellType.CHARGER}
        and (x, y) not in starts
    ]
    if request.benchmark == "C":
        starts = spare + starts
    else:
        starts += spare
    if len(starts) < fleet:
        raise ValueError("Map has too few traversable start cells")
    scene.robots = [
        Robot(id=f"R-{i + 1:02}", name=f"Atlas {i + 1:02}", position=starts[i], home=starts[i])
        for i in range(fleet)
    ]
    # Every robot gets a distinct charging home; all algorithms use this identical map.
    cells = {(c.x, c.y): c for c in scene.warehouse.cells}
    for r in scene.robots:
        cells[r.position] = Cell(x=r.position[0], y=r.position[1], type=CellType.CHARGER)
    scene.warehouse.cells = list(cells.values())
    pickups = [(c.x, c.y) for c in scene.warehouse.cells if c.type == CellType.PICKUP]
    dropoffs = [(c.x, c.y) for c in scene.warehouse.cells if c.type == CellType.DROPOFF]
    if not pickups or not dropoffs:
        raise ValueError("Transport benchmarks require pickup and dropoff stations")
    scene.tasks = [
        TransportTask(
            id=f"T-{i + 1:03}",
            pickup=rng.choice(pickups),
            dropoff=rng.choice(dropoffs),
            priority=rng.randint(1, 10),
        )
        for i in range(request.task_count)
    ]
    return Scenario.model_validate(scene.model_dump())


def run_one(
    base_data: dict[str, Any],
    request_data: dict[str, Any],
    algorithm: str,
    scheduler: str,
    seed: int,
    fleet: int,
) -> dict[str, Any]:
    request = ExperimentRequest.model_validate(request_data)
    scene = prepare(Scenario.model_validate(base_data), request, seed, fleet)
    scene.config = request.config.model_copy(
        update={
            "control": "classical",
            "neural_model_id": None,
            "planner": algorithm,
            "scheduler": scheduler,
            "max_ticks": request.max_ticks or request.config.max_ticks or scene.config.max_ticks,
        }
    )
    began = perf_counter()
    record: dict[str, Any] = {
        "algorithm": algorithm,
        "scheduler": scheduler,
        "seed": seed,
        "robots": fleet,
        "mode": request.mode,
        "benchmark": request.benchmark,
        "source": "measured",
        "optimal": False,
    }
    if request.mode == "mapf":
        grid = Grid(scene.warehouse)
        starts = {r.id: r.position for r in scene.robots}
        free = [
            (x, y) for y in range(grid.height) for x in range(grid.width) if grid.walkable((x, y))
        ]
        rng = random.Random(seed)
        selected = rng.sample(free, fleet)
        goals = dict(zip(starts, selected))
        result = plan(
            grid,
            starts,
            goals,
            algorithm,
            horizon=request.config.horizon,
            max_nodes=request.config.max_nodes,
            timeout=request.config.timeout_seconds,
        )
        success = result.status == "SUCCESS"
        costs = [len(p) - 1 for p in result.paths.values()] if success else []
        moves = (
            sum(sum(a != b for a, b in zip(path, path[1:])) for path in result.paths.values())
            if success
            else 0
        )
        record.update(
            {
                "status": result.status,
                "reason": result.reason,
                "success": success,
                "optimal": result.optimal,
                "starts": starts,
                "goals": goals,
                "paths": result.paths,
                "expanded": result.expanded,
                "metrics": {
                    "makespan": max(costs, default=0),
                    "sum_of_costs": sum(costs),
                    "completed_tasks": fleet if success else 0,
                    "task_completion_rate": 1 if success else 0,
                    "average_task_completion_time": mean(costs) if costs else 0,
                    "total_distance": moves * scene.warehouse.cell_size,
                    "total_waiting": sum(costs) - moves,
                    "planning_time_ms": result.elapsed_ms,
                    "replans": 0,
                    "planning_conflicts": result.conflicts,
                    "executed_collisions": 0,
                    "success": success,
                },
                "first_conflict": asdict(result.first_conflict) if result.first_conflict else None,
            }
        )
    else:
        engine = Engine(scene, f"benchmark-{seed}-{algorithm}-{scheduler}-{fleet}")
        dynamic_point = next(
            (
                (x, y)
                for y in range(1, scene.warehouse.height - 3)
                for x in range(2, scene.warehouse.width - 2)
                if engine.grid.kind((x, y)) == CellType.FLOOR
            ),
            None,
        )
        interruption = None
        while engine.state.status not in {"FAILED", "COMPLETED", "STOPPED"}:
            tick = engine.state.tick
            if (
                request.max_run_seconds is not None
                and perf_counter() - began >= request.max_run_seconds
            ):
                interruption = "WALL_LIMIT"
                break
            if request.benchmark == "D" and tick == 5 and dynamic_point:
                # Fixed exogenous cell/tick. Rejecting occupancy is an explicit scenario outcome.
                try:
                    engine.obstacle(dynamic_point)
                except ValueError as exc:
                    engine.fail(f"Dynamic schedule could not be applied: {exc}")
            engine.step()
        status = "TICK_LIMIT" if engine.tick_limit_reached else interruption or engine.state.status
        record.update(
            {
                "status": status,
                "reason": engine.state.error,
                "success": status == "COMPLETED",
                "planner_status": engine.state.planner_status,
                "metrics": engine.state.metrics.model_dump(),
                "history": engine.state.history,
            }
        )
    record["wall_time_ms"] = (perf_counter() - began) * 1000
    return record


def aggregate(records: list[dict[str, Any]]) -> list[dict[str, Any]]:
    groups: dict[tuple[str, str, int], list[dict[str, Any]]] = {}
    for r in records:
        groups.setdefault((r["algorithm"], r["scheduler"], r["robots"]), []).append(r)
    result = []
    for (algorithm, scheduler, robots), rows in groups.items():
        successful = [r for r in rows if r["success"]]
        summary: dict[str, Any] = {
            "algorithm": algorithm,
            "scheduler": scheduler,
            "robots": robots,
            "runs": len(rows),
            "successful_runs": len(successful),
            "success_rate": len(successful) / len(rows),
            "metrics": {},
        }
        for key in rows[0]["metrics"]:
            if key == "success":
                continue
            # Quality metrics use successful runs; planning runtime includes failures.
            source = rows if key in {"planning_time_ms", "planning_conflicts"} else successful
            values = [r["metrics"][key] for r in source]
            summary["metrics"][key] = {
                "mean": mean(values) if values else None,
                "std": pstdev(values) if values else None,
                "n": len(values),
            }
        result.append(summary)
    return result


def environment() -> dict[str, str]:
    return {
        "python": sys.version,
        "platform": platform.platform(),
        "machine": platform.machine(),
        "timer": "time.perf_counter",
        "engine_version": "0.1.0",
    }
