"""Analyze every completed pair from the predefined study, including failures."""

import csv
import json
import random
from collections import Counter
from pathlib import Path
from statistics import mean
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "docs/experiments/ml-traffic-study"


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
    for config in plan["evaluation"]:
        fleet = config["generator"]["robot_count"]
        job = read(f"comparison-{fleet}-robots.json")
        assert job["status"] == "COMPLETED" and len(job["pairs"]) == config["maps"]
        assert job["model_id"] == model["id"]
        for pair in job["pairs"]:
            assert pair["unseen_layout"]
            assert pair["layout_key"] not in model["train_layouts"] + model["test_layouts"]
            a, b = pair["baseline"], pair["learned"]
            assert a["seed"] == b["seed"] == pair["seed"]
            assert a["metrics"]["executed_collisions"] == b["metrics"]["executed_collisions"] == 0
            scenario = pair["scenario"]
            g = json.loads(scenario["warehouse"]["metadata"]["generator"])
            rows.append(
                {
                    "job_id": job["id"],
                    "fleet": fleet,
                    "seed": pair["seed"],
                    "layout": g["layout"],
                    "width": g["width"],
                    "height": g["height"],
                    "shelf_coverage": float(scenario["warehouse"]["metadata"]["shelf_coverage"]),
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
    # Same physical shelf layouts, tasks and existing robot starts across fleet levels.
    jobs = [read(f"comparison-{n}-robots.json") for n in [4, 8, 12, 16]]
    for index in range(15):
        scenes = [j["pairs"][index]["scenario"] for j in jobs]
        for scene in scenes[1:]:
            assert scene["tasks"] == scenes[0]["tasks"]
            assert scene["robots"][:4] == scenes[0]["robots"]
            assert [c for c in scene["warehouse"]["cells"] if c["type"] == "SHELF"] == [
                c for c in scenes[0]["warehouse"]["cells"] if c["type"] == "SHELF"
            ]
    assert read("dataset-before-evaluation.json") == read("dataset-after-evaluation.json")
    with (OUT / "pairs.csv").open("w", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)
    grouped = {str(n): summarize([r for r in rows if r["fleet"] == n]) for n in [4, 8, 12, 16]}
    training = [r for i in range(1, 4) for r in read(f"training-{i}.json")["runs"]]
    report = {
        "model_id": model["id"],
        "model_samples": model["samples"],
        "model_metrics": model["metrics"],
        "training_attempts": len(training),
        "training_statuses": dict(Counter(r["status"] for r in training)),
        "new_completed_transports": sum(r["metrics"]["completed_tasks"] for r in training),
        "training_baseline_waiting_mean": mean(
            r["metrics"]["total_waiting"] for r in training if r["status"] == "COMPLETED"
        ),
        "by_fleet": grouped,
        "by_layout_exploratory": {
            layout: summarize([r for r in rows if r["layout"] == layout], uncertainty=False)
            for layout in ["aisles", "islands", "mixed"]
        },
        "overall_descriptive": summarize(rows, uncertainty=False),
        "interval_method": "10000 paired bootstrap samples within each fleet, seed 20261113, percentile 2.5/97.5; exploratory, no multiple-testing adjustment; 15 related shelf layouts reused across fleets, no pooled CI",
        "best_successful_pairs": sorted(
            [r for r in rows if r["baseline_status"] == r["ml_status"] == "COMPLETED"],
            key=lambda r: r["delta"],
        )[:5],
        "worst_successful_pairs": sorted(
            [r for r in rows if r["baseline_status"] == r["ml_status"] == "COMPLETED"],
            key=lambda r: r["delta"],
            reverse=True,
        )[:5],
        "failures": [
            r for r in rows if r["baseline_status"] != "COMPLETED" or r["ml_status"] != "COMPLETED"
        ],
    }
    (OUT / "summary.json").write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n")
    print(
        json.dumps(
            {
                k: v
                for k, v in report.items()
                if k not in {"best_successful_pairs", "worst_successful_pairs", "failures"}
            },
            indent=2,
            ensure_ascii=False,
        )
    )


if __name__ == "__main__":
    main()
