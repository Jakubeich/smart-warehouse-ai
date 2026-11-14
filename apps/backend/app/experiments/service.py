import asyncio
from concurrent.futures import ProcessPoolExecutor
from datetime import UTC, datetime
from itertools import product
from typing import Any
from uuid import uuid4

from app.domain.models import Scenario
from app.experiments.runner import aggregate, environment, run_one
from app.persistence.database import Repository
from app.schemas.requests import ExperimentRequest


class Experiments:
    def __init__(self, repository: Repository):
        self.repository = repository
        self.pool = ProcessPoolExecutor(max_workers=2)
        self.jobs: dict[str, dict[str, Any]] = {}
        self.tasks: set[asyncio.Task[None]] = set()

    def create(self, request: ExperimentRequest, scenario: Scenario) -> dict[str, Any]:
        if request.mode == "mapf" and len(request.schedulers) > 1:
            raise ValueError("Static MAPF does not compare task schedulers")
        if len(request.robot_counts) != len(set(request.robot_counts)):
            raise ValueError("Duplicate fleet sizes")
        if any(n < 1 or n > 16 for n in request.robot_counts):
            raise ValueError("Benchmark fleets must contain 1–16 robots")
        if request.mode == "mapf" and request.benchmark in {"D", "F"}:
            raise ValueError("Dynamic obstacles and scheduling require transport mode")
        if len(set(request.algorithms)) != len(request.algorithms) or len(
            set(request.schedulers)
        ) != len(request.schedulers):
            raise ValueError("Duplicate algorithms or schedulers")
        count = (
            len(request.algorithms)
            * len(request.schedulers)
            * len(request.robot_counts)
            * request.repetitions
        )
        if count > 120:
            raise ValueError("Maximum 120 runs per experiment")
        if sum(j["status"] == "RUNNING" for j in self.jobs.values()) >= 2:
            raise ValueError("At most two experiments can run concurrently")
        job: dict[str, Any] = {
            "id": str(uuid4()),
            "name": request.name,
            "status": "RUNNING",
            "created_at": datetime.now(UTC).isoformat(),
            "config": request.model_dump(mode="json"),
            "scenario": scenario.model_dump(mode="json"),
            "results": [],
            "summary": [],
            "total_runs": count,
            "environment": environment(),
        }
        self.jobs[job["id"]] = job
        task = asyncio.create_task(self.run(job, request, scenario))
        self.tasks.add(task)
        task.add_done_callback(self.tasks.discard)
        return job

    async def run(
        self, job: dict[str, Any], request: ExperimentRequest, scenario: Scenario
    ) -> None:
        loop = asyncio.get_running_loop()
        try:
            await asyncio.to_thread(self.repository.save, "experiment", job["id"], dict(job))
            for repeat, fleet, algorithm, scheduler in product(
                range(request.repetitions),
                request.robot_counts,
                request.algorithms,
                request.schedulers,
            ):
                if job["status"] == "CANCELLED":
                    break
                result = await loop.run_in_executor(
                    self.pool,
                    run_one,
                    scenario.model_dump(mode="json"),
                    request.model_dump(mode="json"),
                    algorithm,
                    scheduler,
                    request.seed + repeat,
                    fleet,
                )
                job["results"].append(result)
                job["summary"] = aggregate(job["results"])
                await asyncio.to_thread(self.repository.save, "experiment", job["id"], dict(job))
            if job["status"] != "CANCELLED":
                job["status"] = "COMPLETED"
        except Exception as exc:
            job["status"], job["error"] = "FAILED", f"{type(exc).__name__}: {exc}"
        finally:
            await asyncio.to_thread(self.repository.save, "experiment", job["id"], dict(job))

    async def close(self) -> None:
        for job in self.jobs.values():
            if job["status"] == "RUNNING":
                job["status"] = "CANCELLED"
        if self.tasks:
            await asyncio.gather(*self.tasks, return_exceptions=True)
        self.pool.shutdown(wait=False, cancel_futures=True)
