"""Analyze all predefined route-aware ML comparisons, preserving every failure."""

import csv
import json
import random
from collections import Counter
from pathlib import Path
from statistics import mean
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "docs/experiments/ml-route-study"


def read(name: str) -> Any:
    return json.loads((OUT / name).read_text())


def bootstrap(pairs: list[dict[str, Any]]) -> list[float] | None:
    if len(pairs) < 2:
        return None
    rng = random.Random(20261113)
    estimates = []
    for _ in range(10000):
        draw = rng.choices(pairs, k=len(pairs))
        a, b = sum(p["baseline_makespan"] for p in draw), sum(p["ml_makespan"] for p in draw)
        estimates.append(100 * (a - b) / a)
    estimates.sort()
    return [estimates[249], estimates[9749]]


def summarize(rows: list[dict[str, Any]], uncertainty: bool = True) -> dict[str, Any]:
    good = [r for r in rows if r["baseline_status"] == r["ml_status"] == "COMPLETED"]
    return {
        "pairs": len(rows),
        "successful_pairs": len(good),
        "baseline_successes": sum(r["baseline_status"] == "COMPLETED" for r in rows),
        "ml_successes": sum(r["ml_status"] == "COMPLETED" for r in rows),
        "wins_ties_losses": [
            sum(r["delta"] < 0 for r in good),
            sum(r["delta"] == 0 for r in good),
            sum(r["delta"] > 0 for r in good),
        ],
        "baseline_makespan": mean([r["baseline_makespan"] for r in good]) if good else None,
        "ml_makespan": mean([r["ml_makespan"] for r in good]) if good else None,
        "improvement_percent": 100
        * (sum(r["baseline_makespan"] for r in good) - sum(r["ml_makespan"] for r in good))
        / sum(r["baseline_makespan"] for r in good)
        if good
        else None,
        "bootstrap_95_percent": bootstrap(good) if uncertainty else None,
        "baseline_waiting": mean([r["baseline_waiting"] for r in good]) if good else None,
        "ml_waiting": mean([r["ml_waiting"] for r in good]) if good else None,
        "mean_simulation_compute_ms": {
            m: mean([r[f"{m}_wall_ms"] for r in rows]) for m in ("baseline", "ml")
        },
        "different_assignments": sum(r["different_assignments"] for r in rows),
    }


def main() -> None:
    plan, model = read("plan.json"), read("model.json")
    rows = []
    groups = {}
    for config in plan["evaluation"]:
        name = config["generator"]["name"].split(" / ")[-1]
        job = read(f"comparison-{name}.json")
        assert job["status"] == "COMPLETED" and len(job["pairs"]) == config["maps"]
        assert job["model_id"] == model["id"]
        for pair in job["pairs"]:
            assert pair["unseen_layout"]
            assert pair["layout_key"] not in model["train_layouts"] + model["test_layouts"]
            a, b = pair["baseline"], pair["learned"]
            assert a["seed"] == b["seed"] == pair["seed"]
            assert a["metrics"]["executed_collisions"] == b["metrics"]["executed_collisions"] == 0
            scene = pair["scenario"]
            assert (
                sum(t["pickup"][0] > t["dropoff"][0] for t in scene["tasks"])
                == len(scene["tasks"]) // 2
            )
            rows.append(
                {
                    "condition": name,
                    "job_id": job["id"],
                    "seed": pair["seed"],
                    "fleet": len(scene["robots"]),
                    "tasks": len(scene["tasks"]),
                    "baseline_status": a["status"],
                    "ml_status": b["status"],
                    "baseline_reason": a["reason"],
                    "ml_reason": b["reason"],
                    "baseline_makespan": a["metrics"]["makespan"],
                    "ml_makespan": b["metrics"]["makespan"],
                    "delta": b["metrics"]["makespan"] - a["metrics"]["makespan"],
                    "baseline_waiting": a["metrics"]["total_waiting"],
                    "ml_waiting": b["metrics"]["total_waiting"],
                    "baseline_distance": a["metrics"]["total_distance"],
                    "ml_distance": b["metrics"]["total_distance"],
                    "baseline_completed": a["metrics"]["completed_tasks"],
                    "ml_completed": b["metrics"]["completed_tasks"],
                    "baseline_wall_ms": a["wall_time_ms"],
                    "ml_wall_ms": b["wall_time_ms"],
                    "different_assignments": sum(
                        r != b["assignments"].get(k) for k, r in a["assignments"].items()
                    ),
                }
            )
        groups[name] = summarize([r for r in rows if r["condition"] == name])
    assert read("dataset-before-evaluation.json") == read("dataset-after-evaluation.json")
    with (OUT / "pairs.csv").open("w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)
    training = [r for i in range(1, 7) for r in read(f"training-{i}.json")["runs"]]
    successful = [r for r in rows if r["baseline_status"] == r["ml_status"] == "COMPLETED"]
    report = {
        "model_id": model["id"],
        "feature_version": model["feature_version"],
        "model_samples": model["samples"],
        "model_metrics": model["metrics"],
        "training_attempts": len(training),
        "training_statuses": dict(Counter(r["status"] for r in training)),
        "new_completed_transports": sum(r["metrics"]["completed_tasks"] for r in training),
        "by_condition": groups,
        "overall_descriptive": summarize(rows, uncertainty=False),
        "best_successful_pairs": sorted(successful, key=lambda r: r["delta"])[:5],
        "worst_successful_pairs": sorted(successful, key=lambda r: r["delta"], reverse=True)[:5],
        "failures": [r for r in rows if r not in successful],
        "interval_method": "10000 paired bootstrap resamples within condition; percentile 2.5/97.5, seed20261113; exploratory, unadjusted for multiple comparisons; success-pair subset only",
    }
    (OUT / "summary.json").write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n")
    print(
        json.dumps(
            {
                k: v
                for k, v in report.items()
                if k not in {"best_successful_pairs", "worst_successful_pairs", "failures"}
            },
            ensure_ascii=False,
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
