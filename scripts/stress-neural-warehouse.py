"""Evaluate maximum-size warehouses with the same frozen neural model."""

import argparse
import json
import sys
from collections import Counter
from concurrent.futures import ProcessPoolExecutor, as_completed
from pathlib import Path
from time import perf_counter, process_time
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "apps/backend"))

from app.core.generator import GeneratorRequest, generate  # noqa: E402
from app.domain.models import Scenario  # noqa: E402
from app.neural.policy import NeuralPolicy  # noqa: E402
from app.simulation.engine import Engine  # noqa: E402

LIMIT = 4000


def evaluate(name: str, scene: Scenario, checkpoint: dict[str, Any]) -> dict[str, Any]:
    scene.config.control = "neural"
    scene.config.neural_model_id = None
    engine = Engine(scene, name, policy=NeuralPolicy(checkpoint["model"]))
    started = perf_counter()
    cpu_started = process_time()
    for _ in range(LIMIT):
        engine.step()
        if engine.state.status in {"COMPLETED", "FAILED", "STOPPED"}:
            break
    state = engine.state
    return {
        "case": name,
        "generator": json.loads(scene.warehouse.metadata["generator"]),
        "model": state.neural_last_model_id,
        "status": state.status if state.tick < LIMIT or state.status != "READY" else "TICK_LIMIT",
        "error": state.error,
        "ticks": state.tick,
        "completed": state.metrics.completed_tasks,
        "task_statuses": dict(Counter(t.status for t in state.tasks)),
        "rejected_proposals": state.neural_rejections,
        "executed_collisions": state.metrics.executed_collisions,
        "stall": engine.stalled_ticks >= 30,
        "min_battery_percent": min(r.battery / r.battery_capacity * 100 for r in state.robots),
        "planning_time_ms": state.metrics.planning_time_ms,
        "cpu_seconds": process_time() - cpu_started,
        "elapsed_seconds": perf_counter() - started,
        "final_robots": [
            {"id": r.id, "position": r.position, "goal": r.goal, "mode": r.mode, "wait": r.waiting}
            for r in state.robots
        ],
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--scenario", type=Path, required=True)
    parser.add_argument("--checkpoint", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--workers", type=int, default=4)
    args = parser.parse_args()
    scene = Scenario.model_validate_json(args.scenario.read_text())
    checkpoint = json.loads(args.checkpoint.read_text())
    generator = GeneratorRequest.model_validate_json(scene.warehouse.metadata["generator"])
    changes: list[tuple[str, dict[str, Any]]] = [
        ("reported-geometry-32", {"robot_count": 32}),
        ("wider-2-17", {"passage_width": 2}),
        ("wider-3-17", {"passage_width": 3}),
        ("wider-and-extra-17", {"passage_width": 3, "passage_count": 3}),
        ("open-17", {"bottlenecks": False}),
        ("open-32", {"bottlenecks": False, "robot_count": 32}),
        ("one-way-17", {"traffic": "one_way"}),
        ("new-narrow-32-a", {"seed": 3318493665, "robot_count": 32}),
        ("new-narrow-32-b", {"seed": 3318493666, "robot_count": 32, "layout": "aisles"}),
        ("new-wide-32-a", {"seed": 3318493665, "robot_count": 32, "passage_width": 3}),
        (
            "new-wide-32-b",
            {"seed": 3318493666, "robot_count": 32, "layout": "aisles", "passage_width": 3},
        ),
    ]
    scenarios = {"reported": scene}
    for name, change in changes:
        variant = generate(generator.model_copy(update=change))
        variant.config = scene.config.model_copy(deep=True)
        scenarios[name] = variant
    rows = []
    with ProcessPoolExecutor(max_workers=args.workers) as pool:
        futures = {
            name: pool.submit(evaluate, name, scenario, checkpoint)
            for name, scenario in scenarios.items()
        }
        for future in as_completed(futures.values()):
            row = future.result()
            rows.append(row)
            print(row["case"], row["status"], row["ticks"], row["completed"], flush=True)
            args.output.write_text(
                json.dumps({"tick_limit": LIMIT, "cases": rows}, indent=2) + "\n"
            )


if __name__ == "__main__":
    main()
