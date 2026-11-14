"""Run/resume a predefined bottleneck / opposing-traffic study through the application's real learning API."""

import argparse
import hashlib
import json
import time
import urllib.request
from datetime import UTC, datetime
from pathlib import Path
from typing import Any


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--api", default="http://127.0.0.1:8000/api")
    parser.add_argument("--output", type=Path, default=Path("docs/experiments/ml-route-study"))
    args = parser.parse_args()
    output: Path = args.output
    output.mkdir(parents=True, exist_ok=True)

    def api(path: str, body: dict[str, Any] | None = None) -> Any:
        request = urllib.request.Request(
            args.api + path,
            data=json.dumps(body).encode() if body is not None else None,
            headers={"Content-Type": "application/json"},
        )
        with urllib.request.urlopen(request, timeout=60) as response:
            return json.load(response)

    def save(name: str, value: Any) -> None:
        path = output / name
        temporary = path.with_suffix(path.suffix + ".tmp")
        temporary.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n")
        temporary.replace(path)

    plan_path = output / "plan.json"
    if plan_path.exists():
        plan = json.loads(plan_path.read_text())
    else:
        before = api("/learning")
        generator = {"width": 20, "height": 20, "task_count": 64, "traffic": "bidirectional"}
        conditions = [
            ("one-narrow-4", 4, True, 1, 1),
            ("one-narrow-8", 8, True, 1, 1),
            ("two-narrow-8", 8, True, 2, 1),
            ("two-narrow-12", 12, True, 2, 1),
            ("two-wide-8", 8, True, 2, 2),
            ("open-8", 8, False, 2, 1),
        ]
        plan = {
            "created_at": datetime.now(UTC).isoformat(),
            "question": "Does route-aware ML dispatch help under narrow passages and opposing traffic?",
            "baseline": "priority",
            "limits": {"max_ticks": 4000, "wall_seconds_per_run": 30},
            "conditions": [list(c) for c in conditions],
            "training": [
                {
                    "action": "collect_train",
                    "maps": 15,
                    "seed": 610000 + i * 10000,
                    "max_ticks": 4000,
                    "vary_layouts": True,
                    "generator": {
                        **generator,
                        "name": f"Trénink tras / {name}",
                        "robot_count": fleet,
                        "bottlenecks": narrow,
                        "passage_count": count,
                        "passage_width": width,
                    },
                }
                for i, (name, fleet, narrow, count, width) in enumerate(conditions)
            ],
            "evaluation": [
                {
                    "action": "compare",
                    "maps": 12,
                    "seed": 750000,
                    "baseline": "priority",
                    "max_ticks": 4000,
                    "vary_layouts": True,
                    "generator": {
                        **generator,
                        "name": f"Porovnání tras / {name}",
                        "robot_count": fleet,
                        "bottlenecks": narrow,
                        "passage_count": count,
                        "passage_width": width,
                    },
                }
                for name, fleet, narrow, count, width in conditions
            ],
            "before_model_id": before["active_model_id"],
            "before_dataset": before["dataset"],
            "source_sha256": {
                str(p): hashlib.sha256(p.read_bytes()).hexdigest()
                for folder in ["simulation", "learning", "scheduling", "algorithms", "core"]
                for p in sorted((Path("apps/backend/app") / folder).glob("*.py"))
            },
        }
        save("plan.json", plan)
        save("before-model.json", api(f"/learning/models/{before['active_model_id']}"))
    state_path = output / "progress.json"
    state = json.loads(state_path.read_text()) if state_path.exists() else {"jobs": {}}

    def run(key: str, config: dict[str, Any]) -> dict[str, Any]:
        if key not in state["jobs"]:
            job: dict[str, Any] = api("/learning/jobs", config)
            state["jobs"][key] = job["id"]
            save("progress.json", state)
        job_id = state["jobs"][key]
        last = None
        while True:
            job = api(f"/learning/jobs/{job_id}")
            progress = (job["status"], job["progress"], job["message"])
            if progress != last:
                print(key, job_id, *progress, flush=True)
                last = progress
            if job["status"] not in {"RUNNING", "CANCELLING"}:
                save(key + ".json", job)
                if job["status"] != "COMPLETED":
                    raise RuntimeError(f"{key}: {job.get('error', job['status'])}")
                return job
            time.sleep(2)

    if "model_id" not in state:
        for index, config in enumerate(plan["training"]):
            trained = run(f"training-{index + 1}", config)
        state["model_id"] = trained["model_id"]
        save("progress.json", state)
        save("model.json", api(f"/learning/models/{state['model_id']}"))
        save("dataset-before-evaluation.json", api("/learning")["dataset"])
    for config in plan["evaluation"]:
        condition = config["generator"]["name"].split(" / ")[-1]
        run(f"comparison-{condition}", {**config, "model_id": state["model_id"]})
    after = api("/learning")["dataset"]
    save("dataset-after-evaluation.json", after)
    before_eval = json.loads((output / "dataset-before-evaluation.json").read_text())
    if after != before_eval:
        raise RuntimeError("Dataset changed during evaluation; inspect concurrent live runs.")
    print("Study completed; dataset unchanged by evaluation. Model:", state["model_id"], flush=True)


if __name__ == "__main__":
    main()
