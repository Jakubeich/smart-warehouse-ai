# ruff: noqa: E402
"""Screen smaller updates toward the reward-trained model, then run a fresh test."""

import argparse
import json
import runpy
from pathlib import Path
from typing import Any

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
parent = runpy.run_path(str(ROOT / "scripts/study-neural-yield.py"))
save, maps, geometry_key, evaluate, compare, summarize = (
    parent[key] for key in ("save", "maps", "geometry_key", "evaluate", "compare", "summarize")
)

from app.domain.models import Scenario
from app.neural.policy import NeuralPolicy, weight_id


def shortened_update(
    base: dict[str, Any], trained: dict[str, Any], fraction: float
) -> dict[str, Any]:
    layers = [
        {
            field: (
                np.asarray(original[field])
                + fraction * (np.asarray(learned[field]) - np.asarray(original[field]))
            ).tolist()
            for field in ("bias", "weights")
        }
        for original, learned in zip(
            base["model"]["layers"], trained["model"]["layers"], strict=True
        )
    ]
    return {**trained, "model": {**trained["model"], "id": weight_id(layers), "layers": layers}}


def accepted(summary: dict[str, Any]) -> bool:
    before, after = summary["before"], summary["after"]
    return bool(
        summary["both_completed"]
        and after["completed"] >= before["completed"]
        and after["stalls_in_passage_zone"] <= before["stalls_in_passage_zone"]
        and after["scenarios_with_passage_wait_ge_10"]
        <= before["scenarios_with_passage_wait_ge_10"]
        and after["mean_ticks_both_completed"] < before["mean_ticks_both_completed"]
    )


def main() -> None:
    experiments = ROOT / "docs/experiments"
    study = experiments / "neural-yield-study"
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=study / "smaller-update")
    out = parser.parse_args().output
    out.mkdir(parents=True, exist_ok=False)
    base = json.loads((study / "before-checkpoint.json").read_text())
    trained = json.loads((study / "after-checkpoint.json").read_text())
    plan = json.loads((study / "plan.json").read_text())
    validation = [Scenario.model_validate(scene) for scene in plan["validation"] + plan["test"]]
    reference = [
        entry["before"]
        for file in ("yield-16-validation.json", "pairs.json")
        for entry in json.loads((study / file).read_text())
    ]
    assert [
        entry["seed"]
        for file in ("yield-16-validation.json", "pairs.json")
        for entry in json.loads((study / file).read_text())
    ] == [scene.seed for scene in validation]
    original = runpy.run_path(str(ROOT / "scripts/train-neural-fleet.py"))["scenes"](810000, 36)
    excluded = {geometry_key(scene) for scene in original}
    for source in ("neural-online-study", "neural-speed-study", "neural-yield-study"):
        existing = json.loads((experiments / source / "plan.json").read_text())
        for kind in ("train", "validation", "test"):
            excluded.update(
                geometry_key(Scenario.model_validate(s)) for s in existing.get(kind, [])
            )
    old = json.loads((experiments / "neural-fleet/pairs.json").read_text())
    excluded.update(geometry_key(Scenario.model_validate(p["scenario"])) for p in old["pairs"])
    testing = maps(64, 1240000, excluded)
    fractions = (0.10, 0.25, 0.50, 0.75)
    save(
        out / "plan.json",
        {
            "base": base["model"]["id"],
            "trained": trained["model"]["id"],
            "fractions": fractions,
            "validation_seeds": [scene.seed for scene in validation],
            "selection": "Only select models with no aggregate regression in completion, passage stalls "
            "or long-wait maps and a faster mean on joint completions. Among qualifying "
            "models choose the largest mean time saving. Use only that model on fresh maps.",
            "test": [scene.model_dump(mode="json") for scene in testing],
        },
    )
    results = []
    for fraction in fractions:
        candidate = shortened_update(base, trained, fraction)
        policy = NeuralPolicy(candidate["model"])
        pairs = compare(validation, reference, policy)
        measures = summarize(pairs)
        save(out / f"validation-{fraction}.json", pairs)
        results.append({"fraction": fraction, "id": policy.id, **measures})
        save(out / "validation-summary.json", results)
        print(fraction, accepted(measures), measures["after"], flush=True)
    eligible = [r for r in results if accepted(r)]
    if not eligible:
        save(
            out / "summary.json",
            {"selected": None, "reason": "No candidate met both evaluation goals."},
        )
        return
    chosen = min(
        eligible,
        key=lambda r: (
            r["after"]["mean_ticks_both_completed"] - r["before"]["mean_ticks_both_completed"]
        ),
    )
    final = shortened_update(base, trained, chosen["fraction"])
    save(out / "candidate.json", final)
    print("Frozen selection:", chosen["fraction"], final["model"]["id"], flush=True)
    policy = NeuralPolicy(base["model"])
    reference = [evaluate(scene, policy) for scene in testing]
    pairs = compare(testing, reference, NeuralPolicy(final["model"]))
    save(out / "pairs.json", pairs)
    measures = summarize(pairs)
    save(
        out / "summary.json",
        {
            "selected": chosen["fraction"],
            "model": final["model"]["id"],
            "accepted": accepted(measures),
            **measures,
        },
    )


if __name__ == "__main__":
    main()
