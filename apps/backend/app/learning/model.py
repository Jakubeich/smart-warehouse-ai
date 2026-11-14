"""Versioned random-forest residual model. Portable JSON trees, never pickle."""

import json
from datetime import UTC, datetime
from hashlib import sha256
from math import isfinite
from typing import Any
from uuid import uuid4

from app.learning.features import (
    FEATURE_NAMES,
    FEATURE_VERSION,
    LEGACY_FEATURE_NAMES,
    geometric_eta,
)

MIN_SAMPLES = 60
MIN_LAYOUTS = 5


class EtaModel:
    def __init__(self, artifact: dict[str, Any]):
        version = artifact.get("feature_version")
        expected = LEGACY_FEATURE_NAMES if version == 1 else FEATURE_NAMES
        if version not in {1, FEATURE_VERSION} or artifact.get("features") != expected:
            raise ValueError("Model používá nekompatibilní vstupní příznaky. Přetrénujte jej.")
        if not artifact.get("trees"):
            raise ValueError("Model neobsahuje natrénované stromy.")
        self.artifact = artifact
        self.id: str = artifact["id"]
        self.feature_count = len(expected)

    def predict(self, values: list[float]) -> float:
        if len(values) not in {self.feature_count, len(FEATURE_NAMES)} or not all(
            isfinite(x) for x in values
        ):
            raise ValueError("Neplatné vstupy odhadu přepravy.")
        values = values[: self.feature_count]
        # sklearn trees compare float32 inputs; match them exactly without importing
        # NumPy/scikit-learn in every live simulation worker.
        import struct

        x = [struct.unpack("f", struct.pack("f", value))[0] for value in values]
        predictions = []
        for tree in self.artifact["trees"]:
            node = 0
            while tree["left"][node] != -1:
                node = (
                    tree["left"][node]
                    if x[tree["feature"][node]] <= tree["threshold"][node]
                    else tree["right"][node]
                )
            predictions.append(tree["value"][node])
        return float(geometric_eta(values) + max(0.0, sum(predictions) / len(predictions)))


def train(episodes: list[dict[str, Any]], seed: int = 42) -> dict[str, Any]:
    import numpy as np
    import sklearn
    from sklearn.ensemble import RandomForestRegressor
    from sklearn.metrics import mean_absolute_error, mean_squared_error
    from sklearn.model_selection import GroupShuffleSplit

    usable = [
        ep
        for ep in episodes
        if ep.get("feature_version") == FEATURE_VERSION and ep.get("purpose") != "evaluation"
    ]
    rows = [(ep["layout_key"], ep["id"], row) for ep in usable for row in ep["samples"]]
    # Split entire layouts, including every episode recorded on each one.
    if len(rows) < MIN_SAMPLES or len({r[0] for r in rows}) < MIN_LAYOUTS:
        raise ValueError(
            f"Trénink potřebuje alespoň {MIN_SAMPLES} dokončených přeprav z {MIN_LAYOUTS} různých map. Spusťte sběr dat."
        )
    x = np.asarray([r[2]["features"] for r in rows], dtype=np.float64)
    y = np.asarray([r[2]["actual_ticks"] for r in rows], dtype=np.float64)
    base = np.asarray([geometric_eta(r[2]["features"]) for r in rows])
    groups = [r[0] for r in rows]
    train_ids, test_ids = next(
        GroupShuffleSplit(n_splits=1, test_size=0.25, random_state=seed).split(x, y, groups)
    )
    forest = RandomForestRegressor(
        n_estimators=96, max_depth=12, min_samples_leaf=3, random_state=seed, n_jobs=1
    )
    forest.fit(x[train_ids], np.maximum(0.0, y[train_ids] - base[train_ids]))
    predicted = base[test_ids] + np.maximum(0.0, forest.predict(x[test_ids]))
    trees = [
        {
            "left": t.tree_.children_left.tolist(),
            "right": t.tree_.children_right.tolist(),
            "feature": t.tree_.feature.tolist(),
            "threshold": t.tree_.threshold.tolist(),
            "value": t.tree_.value[:, 0, 0].tolist(),
        }
        for t in forest.estimators_
    ]
    artifact: dict[str, Any] = {
        "id": str(uuid4()),
        "created_at": datetime.now(UTC).isoformat(),
        "algorithm": "RandomForestRegressor",
        "feature_version": FEATURE_VERSION,
        "features": FEATURE_NAMES,
        "trees": trees,
        "seed": seed,
        "sklearn_version": sklearn.__version__,
        "target": "assignment_to_unload_ticks",
        "dataset_hash": sha256(json.dumps(rows, sort_keys=True).encode()).hexdigest(),
        "episode_ids": sorted({r[1] for r in rows}),
        "samples": len(rows),
        "train_samples": len(train_ids),
        "test_samples": len(test_ids),
        "train_layouts": sorted({groups[i] for i in train_ids}),
        "test_layouts": sorted({groups[i] for i in test_ids}),
        "metrics": {
            "mae": float(mean_absolute_error(y[test_ids], predicted)),
            "rmse": float(np.sqrt(mean_squared_error(y[test_ids], predicted))),
            "baseline_mae": float(mean_absolute_error(y[test_ids], base[test_ids])),
            "baseline_rmse": float(np.sqrt(mean_squared_error(y[test_ids], base[test_ids]))),
        },
        "feature_importance": dict(zip(FEATURE_NAMES, forest.feature_importances_.tolist())),
        "validation_predictions": [
            {"actual": float(y[i]), "predicted": float(p), "baseline": float(base[i])}
            for i, p in zip(test_ids[:200], predicted[:200])
        ],
        "training_range": {
            name: [float(x[train_ids, j].min()), float(x[train_ids, j].max())]
            for j, name in enumerate(FEATURE_NAMES)
        },
    }
    # Portable inference must reproduce the fitted estimator on held-out examples.
    exported = EtaModel(artifact)
    if not np.allclose([exported.predict(x[i].tolist()) for i in test_ids], predicted, atol=1e-6):
        raise ValueError("Export modelu neodpovídá natrénovaným predikcím.")
    return artifact


def summary(artifact: dict[str, Any]) -> dict[str, Any]:
    return {key: value for key, value in artifact.items() if key not in {"trees", "episode_ids"}}
