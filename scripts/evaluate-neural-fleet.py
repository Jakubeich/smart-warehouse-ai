# ruff: noqa: E402
"""Run measured classical/neural pairs on fixed generated test scenarios."""

import argparse
import json
import sys
from pathlib import Path
from statistics import mean
from time import perf_counter
from typing import Any, Literal

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "apps/backend"))

from app.core.demos import demo
from app.core.generator import GeneratorRequest, generate, layout_key
from app.domain.models import Scenario
from app.neural.policy import MODEL_PATH, REPORT_PATH, load_policy
from app.simulation.engine import Engine


def run(scene: Scenario, mode: str) -> dict[str, Any]:
    configured = scene.model_copy(deep=True)
    configured.config.control = "neural" if mode == "neural" else "classical"
    engine = Engine(configured, f"{mode}-{scene.seed}")
    start = perf_counter()
    counts: dict[str, int] = {}
    for _ in range(2200):
        s = engine.step()
        for d in s.neural_decisions:
            counts[d.action] = counts.get(d.action, 0) + 1
        if s.status in {"COMPLETED", "FAILED"}:
            break
    return {
        "status": s.status if s.status in {"COMPLETED", "FAILED"} else "TICK_LIMIT",
        "reason": s.error,
        "metrics": s.metrics.model_dump(),
        "decisions": counts,
        "rejections": s.neural_rejections,
        "wall_seconds": perf_counter() - start,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--seed", type=int, default=920000)
    parser.add_argument("--maps", type=int, default=24)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--demos", action="store_true")
    parser.add_argument("--publish-summary", action="store_true")
    args = parser.parse_args()
    seen = set(json.loads(MODEL_PATH.read_text())["training"]["layout_keys"])
    pairs = []
    layouts: tuple[Literal["aisles", "islands", "mixed"], ...] = ("mixed", "aisles", "islands")
    for i in range(args.maps + (3 if args.demos else 0)):
        seed = args.seed + i
        if i >= args.maps:
            scene = demo(["small", "medium", "large"][i - args.maps], seed=seed)
            condition = "demo"
        else:
            condition = ("open", "narrow", "wide")[i % 3]
            scene = generate(
                GeneratorRequest(
                    seed=seed,
                    width=20,
                    height=18,
                    task_count=20,
                    robot_count=[4, 6, 8, 12][(i // 3) % 4],
                    layout=layouts[i % 3],
                    density=0.22,
                    traffic="bidirectional",
                    bottlenecks=condition != "open",
                    passage_count=1 + (i // 6) % 2,
                    passage_width=2 if condition == "wide" else 1,
                )
            )
            if i % 3 == 0:
                scene.robots[0].battery = 12
        key = layout_key(scene.warehouse)
        assert condition == "demo" or key not in seen
        classical, neural = run(scene, "classical"), run(scene, "neural")
        assert (
            classical["metrics"]["executed_collisions"]
            == neural["metrics"]["executed_collisions"]
            == 0
        )
        pairs.append(
            {
                "condition": condition,
                "seed": seed,
                "layout": key,
                "unseen": key not in seen,
                "scenario": scene.model_dump(mode="json"),
                "classical": classical,
                "neural": neural,
            }
        )
        print(
            seed,
            condition,
            len(scene.robots),
            classical["status"],
            classical["metrics"]["makespan"],
            neural["status"],
            neural["metrics"]["makespan"],
            neural["metrics"]["completed_tasks"],
            neural["rejections"],
            neural["reason"] or "",
            flush=True,
        )
    model_id = load_policy().id
    if args.output:
        args.output.write_text(
            json.dumps({"model": model_id, "pairs": pairs}, ensure_ascii=False) + "\n"
        )

    test_pairs = [pair for pair in pairs if pair["unseen"]]
    both = [
        pair
        for pair in test_pairs
        if pair["classical"]["status"] == pair["neural"]["status"] == "COMPLETED"
    ]
    summary = {
        "model": model_id,
        "seed": args.seed,
        "pairs": len(test_pairs),
        "both_completed": len(both),
        "completed": {
            method: sum(pair[method]["status"] == "COMPLETED" for pair in test_pairs)
            for method in ("classical", "neural")
        },
        "mean_ticks": {
            method: mean([pair[method]["metrics"]["makespan"] for pair in both]) if both else None
            for method in ("classical", "neural")
        },
        "executed_collisions": sum(
            pair[method]["metrics"]["executed_collisions"]
            for pair in test_pairs
            for method in ("classical", "neural")
        ),
    }
    if args.publish_summary:
        REPORT_PATH.write_text(json.dumps(summary, indent=2) + "\n")
    print(json.dumps(summary), flush=True)


if __name__ == "__main__":
    main()
