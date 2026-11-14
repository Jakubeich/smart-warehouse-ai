"""Run reproducible experiments without HTTP, a database or a renderer."""

import argparse
import json
from itertools import product
from pathlib import Path

from app.domain.models import Scenario
from app.experiments.runner import aggregate, environment, run_one
from app.schemas.requests import ExperimentRequest


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--scenario", type=Path, required=True)
    parser.add_argument("--config", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    scene = Scenario.model_validate_json(args.scenario.read_text())
    request = ExperimentRequest.model_validate_json(args.config.read_text())
    records = []
    for repeat, fleet, algorithm, scheduler in product(
        range(request.repetitions), request.robot_counts, request.algorithms, request.schedulers
    ):
        result = run_one(
            scene.model_dump(mode="json"),
            request.model_dump(mode="json"),
            algorithm,
            scheduler,
            request.seed + repeat,
            fleet,
        )
        records.append(result)
        print(f"{algorithm:12s} fleet={fleet:2d} seed={request.seed + repeat} {result['status']}")
    output = {
        "config": request.model_dump(mode="json"),
        "scenario": scene.model_dump(mode="json"),
        "environment": environment(),
        "results": records,
        "summary": aggregate(records),
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(output, indent=2) + "\n")


if __name__ == "__main__":
    main()
