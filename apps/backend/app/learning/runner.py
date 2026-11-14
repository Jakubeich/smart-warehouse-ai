"""Measured training episodes and paired evaluations through the same tick engine."""

import hashlib
import json
from statistics import mean
from time import perf_counter
from typing import Any
from uuid import uuid4

from app.domain.models import Scenario
from app.learning.model import EtaModel
from app.simulation.engine import Engine


def run_episode(
    data: dict[str, Any],
    scheduler: str,
    purpose: str,
    artifact: dict[str, Any] | None = None,
    max_ticks: int = 1800,
) -> dict[str, Any]:
    scene = Scenario.model_validate(data)
    scene.config = scene.config.model_copy(
        update={
            "control": "classical",
            "neural_model_id": None,
            "scheduler": scheduler,
            "ml_model_id": artifact["id"] if artifact else None,
        }
    )
    engine = Engine(scene, str(uuid4()), EtaModel(artifact) if artifact else None)
    began = perf_counter()
    limit = "TICK_LIMIT"
    for _ in range(max_ticks):
        if perf_counter() - began > 30:
            limit = "TIMEOUT"
            break
        engine.step()
        if engine.state.status in {"COMPLETED", "FAILED", "STOPPED"}:
            break
    state = engine.state
    status = state.status if state.status in {"COMPLETED", "FAILED", "STOPPED"} else limit
    episode = engine.learning_episode(purpose)
    if purpose == "training":
        # Identical generated episodes are upserted instead of inflating the dataset.
        identity = json.dumps(
            {
                "scenario": scene.model_dump(
                    mode="json", exclude={"config": {"control", "neural_model_id"}}
                ),
                "feature_version": episode["feature_version"],
            },
            sort_keys=True,
        )
        episode["id"] = "generated-" + hashlib.sha256(identity.encode()).hexdigest()[:32]
    episode["status"] = status
    return {
        "episode": episode,
        "scheduler": scheduler,
        "seed": scene.seed,
        "status": status,
        "reason": state.error,
        "source": "measured",
        "metrics": state.metrics.model_dump(),
        "wall_time_ms": (perf_counter() - began) * 1000,
        "mean_transport_ticks": mean([r["actual_ticks"] for r in episode["samples"]])
        if episode["samples"]
        else None,
        "assignments": {t.id: t.assigned_robot for t in state.tasks},
        "decision_examples": [d.model_dump() for d in state.assignment_decisions[-3:]],
    }


def comparison_summary(pairs: list[dict[str, Any]]) -> dict[str, Any]:
    successful = [
        p for p in pairs if p["baseline"]["status"] == p["learned"]["status"] == "COMPLETED"
    ]
    metrics = {}
    for field in [
        "makespan",
        "average_task_completion_time",
        "total_waiting",
        "total_distance",
        "planning_time_ms",
    ]:
        a = [p["baseline"]["metrics"][field] for p in successful]
        b = [p["learned"]["metrics"][field] for p in successful]
        av, bv = (mean(a), mean(b)) if a else (None, None)
        metrics[field] = {
            "baseline": av,
            "learned": bv,
            "delta": bv - av if av is not None and bv is not None else None,
            "improvement_percent": (av - bv) / av * 100 if av and bv is not None else None,
        }
    return {
        "pairs": len(pairs),
        "successful_pairs": len(successful),
        "baseline_successes": sum(p["baseline"]["status"] == "COMPLETED" for p in pairs),
        "learned_successes": sum(p["learned"]["status"] == "COMPLETED" for p in pairs),
        "different_assignments": sum(
            sum(
                r != p["learned"]["assignments"].get(k)
                for k, r in p["baseline"]["assignments"].items()
            )
            for p in pairs
        ),
        "metrics": metrics,
    }
