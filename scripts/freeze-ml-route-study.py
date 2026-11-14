"""Freeze the measured dataset and reproduce the model without changing the active model."""

import gzip
import hashlib
import json
import platform
import sys
from collections import Counter
from pathlib import Path
from statistics import mean
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "docs/experiments/ml-route-study"
sys.path.insert(0, str(ROOT / "apps/backend"))

from app.learning.features import ROUTE_FEATURE_NAMES  # noqa: E402
from app.learning.model import train  # noqa: E402
from app.persistence.database import Repository  # noqa: E402


def read(name: str) -> Any:
    return json.loads((OUT / name).read_text())


def save(name: str, value: Any) -> None:
    (OUT / name).write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n")


def diagnostics(episodes: list[dict[str, Any]]) -> dict[str, Any]:
    samples = [s for ep in episodes for s in ep["samples"]]
    delays = [s["actual_ticks"] - s["geometric_ticks"] for s in samples]
    return {
        "episodes": len(episodes),
        "samples": len(samples),
        "statuses": dict(Counter(ep["status"] for ep in episodes)),
        "unfinished_assignments": sum(ep["unfinished"] for ep in episodes),
        "positive_delay_samples": sum(d > 0 for d in delays),
        "mean_delay_ticks": mean(delays),
        "max_delay_ticks": max(delays),
    }


def main() -> None:
    model, plan = read("model.json"), read("plan.json")
    dataset_path = OUT / "training-episodes.json.gz"
    if dataset_path.exists():
        episodes = json.loads(gzip.decompress(dataset_path.read_bytes()))
    else:
        ids = set(model["episode_ids"])
        episodes = [ep for ep in Repository().list("ml_episode") if ep["id"] in ids]
    rows = [(ep["layout_key"], ep["id"], s) for ep in episodes for s in ep["samples"]]
    dataset_hash = hashlib.sha256(json.dumps(rows, sort_keys=True).encode()).hexdigest()
    assert dataset_hash == model["dataset_hash"], "Dataset changed or episode order differs"
    assert len(rows) == model["samples"]
    assert {ep["id"] for ep in episodes} == set(model["episode_ids"])
    source_matches = {
        name: hashlib.sha256((ROOT / name).read_bytes()).hexdigest() == expected
        for name, expected in plan["source_sha256"].items()
    }
    assert all(source_matches.values()), "Study source changed"
    if not dataset_path.exists():
        dataset_path.write_bytes(gzip.compress(json.dumps(episodes).encode(), mtime=0))
    reproduced = train(episodes, seed=model["seed"])
    keys = [
        "trees",
        "metrics",
        "dataset_hash",
        "train_layouts",
        "test_layouts",
        "feature_importance",
    ]
    checks = {key: reproduced[key] == model[key] for key in keys}
    assert all(checks.values())
    # Model episode IDs include only episodes with a completed label. Keep the
    # zero-completion failed attempt separately, too, for unbiased diagnostics.
    attempts_path = OUT / "study-episodes.json.gz"
    if attempts_path.exists():
        training = json.loads(gzip.decompress(attempts_path.read_bytes()))
    else:
        expected = {
            (config["generator"]["name"], config["seed"] + i)
            for config in plan["training"]
            for i in range(config["maps"])
        }
        training = [
            ep
            for ep in Repository().list("ml_episode")
            if ep.get("feature_version") == 2
            and (ep["scenario"]["name"], ep["scenario"]["seed"]) in expected
        ]
    assert len(training) == 90
    if not attempts_path.exists():
        attempts_path.write_bytes(gzip.compress(json.dumps(training).encode(), mtime=0))
    diagnostic = {
        "model_id": model["id"],
        "dataset_hash": dataset_hash,
        "environment": {
            "python": sys.version,
            "platform": platform.platform(),
            "sklearn": model["sklearn_version"],
        },
        "all_model_data": diagnostics(episodes),
        "new_training": diagnostics(training),
        "new_training_by_condition": {
            name: diagnostics(
                [ep for ep in training if ep["scenario"]["name"].endswith(" / " + name)]
            )
            for name, *_ in plan["conditions"]
        },
        "route_feature_importance_sum": sum(
            model["feature_importance"][f] for f in ROUTE_FEATURE_NAMES
        ),
        "route_feature_nonzero_samples": {
            f: sum(s["features"][model["features"].index(f)] > 0 for _, _, s in rows)
            for f in ROUTE_FEATURE_NAMES
        },
    }
    save("training-diagnostics.json", diagnostic)
    save(
        "reproducibility.json",
        {
            "model_id": model["id"],
            "dataset_hash": dataset_hash,
            "checks": checks,
            "source_hash_matches": source_matches,
        },
    )
    print(
        json.dumps(
            {
                "reproduced": checks,
                "training": diagnostic["new_training"],
                "by_condition": diagnostic["new_training_by_condition"],
            },
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
