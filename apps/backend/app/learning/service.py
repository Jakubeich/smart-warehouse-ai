"""Persistent dataset/model registry with bounded background jobs and frozen evaluations."""

import asyncio
from concurrent.futures import ProcessPoolExecutor
from datetime import UTC, datetime
from typing import Any, Literal
from uuid import uuid4

from pydantic import Field

from app.core.generator import GeneratorRequest, generate, layout_key
from app.domain.models import Model, Scenario
from app.learning.features import FEATURE_VERSION
from app.learning.model import MIN_LAYOUTS, MIN_SAMPLES, EtaModel, summary, train
from app.learning.runner import comparison_summary, run_episode
from app.persistence.database import Repository


class LearningRequest(Model):
    action: Literal["collect_train", "train", "compare"]
    maps: int = Field(default=12, ge=1, le=30)
    seed: int = Field(default=2026, ge=0, le=2**32 - 1)
    generator: GeneratorRequest = Field(default_factory=GeneratorRequest)
    vary_layouts: bool = True
    model_id: str | None = None
    scenario_id: str | None = None
    baseline: Literal["priority", "nearest", "hungarian"] = "priority"
    max_ticks: int | None = Field(default=None, ge=1)


class Learning:
    def __init__(self, repository: Repository):
        self.repository = repository
        self.pool = ProcessPoolExecutor(max_workers=1)
        self.jobs: dict[str, dict[str, Any]] = {}
        self.tasks: set[asyncio.Task[None]] = set()
        self.creation_lock = asyncio.Lock()

    def active_model(self, model_id: str | None = None) -> EtaModel:
        if model_id is None:
            model_id = (self.repository.get("ml_settings", "default") or {}).get("active_model_id")
        data = self.repository.get("ml_model", model_id) if model_id else None
        if data is None:
            raise ValueError("Nejdříve natrénujte model ve stránce Strojové učení.")
        return EtaModel(data)

    def overview(self) -> dict[str, Any]:
        episodes = self.repository.list("ml_episode")
        usable = [
            e
            for e in episodes
            if e.get("purpose") != "evaluation" and e.get("feature_version") == FEATURE_VERSION
        ]
        models = self.repository.list("ml_model")
        return {
            "feature_version": FEATURE_VERSION,
            "archived_samples": sum(
                len(e["samples"]) for e in episodes if e.get("feature_version") != FEATURE_VERSION
            ),
            "dataset": {
                "episodes": len(usable),
                "samples": sum(len(e["samples"]) for e in usable),
                "layouts": len({e["layout_key"] for e in usable if e["samples"]}),
                "unfinished": sum(e.get("unfinished", 0) for e in usable),
                "failed_runs": sum(
                    e["status"] in {"FAILED", "TIMEOUT", "TICK_LIMIT"} for e in usable
                ),
                "min_samples": MIN_SAMPLES,
                "min_layouts": MIN_LAYOUTS,
            },
            "active_model_id": (self.repository.get("ml_settings", "default") or {}).get(
                "active_model_id"
            ),
            "models": [summary(m) for m in models[:10]],
            "jobs": [
                {k: v for k, v in job.items() if k not in {"pairs", "runs"}}
                for job in self.repository.list("ml_job")[:20]
            ],
        }

    def collect(self, episode: dict[str, Any]) -> None:
        # Save the same episode key after each completed task: repeated publication
        # cannot duplicate labels. A reset receives a new episode ID.
        self.repository.save("ml_episode", episode["id"], episode)

    async def create(self, request: LearningRequest) -> dict[str, Any]:
        async with self.creation_lock:
            return await self._create(request)

    async def _create(self, request: LearningRequest) -> dict[str, Any]:
        if any(j["status"] in {"RUNNING", "CANCELLING"} for j in self.jobs.values()):
            raise ValueError("Už běží učení nebo porovnání. Počkejte na dokončení nebo je zrušte.")
        artifact = None
        scenario = None
        if request.action == "compare":
            artifact = (await asyncio.to_thread(self.active_model, request.model_id)).artifact
            if request.scenario_id:
                if request.maps != 1:
                    raise ValueError(
                        "Uložený scénář porovnejte jedním párem. Pro více různých map zvolte generátor."
                    )
                raw = await asyncio.to_thread(self.repository.get, "scenario", request.scenario_id)
                if raw is None:
                    raise ValueError("Vybraný scénář neexistuje.")
                scenario = Scenario.model_validate(raw)
        job: dict[str, Any] = {
            "id": str(uuid4()),
            "action": request.action,
            "status": "RUNNING",
            "created_at": datetime.now(UTC).isoformat(),
            "config": request.model_dump(mode="json"),
            "progress": 0,
            "total": 1 if request.action == "train" else request.maps,
            "message": "Připravuji výpočet",
            "runs": [],
            "pairs": [],
            "summary": None,
            "model_id": artifact["id"] if artifact else None,
        }
        await asyncio.to_thread(self.repository.save, "ml_job", job["id"], job)
        self.jobs[job["id"]] = job
        task = asyncio.create_task(self.run(job, request, artifact, scenario))
        self.tasks.add(task)
        task.add_done_callback(self.tasks.discard)
        return job

    def cancel(self, job_id: str) -> dict[str, Any]:
        job = self.jobs.get(job_id)
        if not job:
            raise ValueError("Tato úloha již neběží.")
        if job["status"] == "RUNNING":
            job["status"] = "CANCELLING"
            job["message"] = "Zastavuji po aktuálním běhu"
        return job

    async def persist(self, job: dict[str, Any]) -> None:
        import copy

        await asyncio.to_thread(self.repository.save, "ml_job", job["id"], copy.deepcopy(job))

    async def run(
        self,
        job: dict[str, Any],
        request: LearningRequest,
        artifact: dict[str, Any] | None,
        saved: Scenario | None,
    ) -> None:
        loop = asyncio.get_running_loop()
        try:
            seen_layouts = (
                set(artifact["train_layouts"] + artifact["test_layouts"]) if artifact else set()
            )
            for index in range(0 if request.action == "train" else request.maps):
                if job["status"] == "CANCELLING":
                    break
                seed = (request.seed + index) % (2**32)
                parameters = request.generator.model_copy(update={"seed": seed})
                if request.vary_layouts and saved is None:
                    parameters.width = max(12, min(64, parameters.width + [-4, 0, 4][index % 3]))
                    parameters.height = max(
                        10, min(64, parameters.height + [-2, 0, 2][(index // 3) % 3])
                    )
                    layouts: list[Literal["aisles", "islands", "mixed"]] = [
                        "aisles",
                        "islands",
                        "mixed",
                    ]
                    parameters.layout = layouts[index % 3]
                    parameters.density = [0.12, 0.22, 0.32][(index // 3) % 3]
                if saved:
                    scene = saved.model_copy(deep=True)
                    seed = scene.seed
                    # Identical full initial state for both methods, including task priorities.
                else:
                    scene = await asyncio.to_thread(generate, parameters)
                key = layout_key(scene.warehouse)
                if request.action == "compare" and saved is None and key in seen_layouts:
                    raise ValueError(
                        "Generovaná testovací mapa už byla použita při tréninku/validaci. Zvolte jiný seed."
                    )
                job["message"] = (
                    f"{'Porovnávám' if request.action == 'compare' else 'Simuluji'} mapu {index + 1} / {request.maps}"
                )
                await self.persist(job)
                if request.action == "collect_train":
                    scheduler = ["nearest", "priority", "hungarian"][index % 3]
                    result = await loop.run_in_executor(
                        self.pool,
                        run_episode,
                        scene.model_dump(mode="json"),
                        scheduler,
                        "training",
                        None,
                        request.max_ticks,
                    )
                    await asyncio.to_thread(self.collect, result.pop("episode"))
                    job["runs"].append(result)
                else:
                    pair: dict[str, Any] = {
                        "seed": seed,
                        "layout_key": key,
                        "unseen_layout": key not in seen_layouts,
                        "scenario": scene.model_dump(mode="json"),
                    }
                    # Finish the pair before cancelling so no unpaired result is silently compared.
                    for key_name, scheduler in [
                        ("baseline", request.baseline),
                        ("learned", "learned"),
                    ]:
                        result = await loop.run_in_executor(
                            self.pool,
                            run_episode,
                            scene.model_dump(mode="json"),
                            scheduler,
                            "evaluation",
                            artifact if scheduler == "learned" else None,
                            request.max_ticks,
                        )
                        result.pop(
                            "episode"
                        )  # Evaluation observations never enter the training dataset.
                        pair[key_name] = result
                    job["pairs"].append(pair)
                    job["summary"] = comparison_summary(job["pairs"])
                job["progress"] += 1
                await self.persist(job)
            if job["status"] == "CANCELLING":
                job["status"], job["message"] = (
                    "CANCELLED",
                    "Úloha zrušena; dokončené výsledky zůstaly uložené.",
                )
            elif request.action in {"collect_train", "train"}:
                job["message"] = "Trénuji model a ověřuji jej na oddělených mapách"
                await self.persist(job)
                episodes = await asyncio.to_thread(self.repository.list, "ml_episode")
                trained = await loop.run_in_executor(self.pool, train, episodes, request.seed)
                if job["status"] == "CANCELLING":
                    job["status"], job["message"] = (
                        "CANCELLED",
                        "Trénink zrušen; aktivní model zůstal zachovaný.",
                    )
                else:
                    await asyncio.to_thread(
                        self.repository.save, "ml_model", trained["id"], trained
                    )
                    await asyncio.to_thread(
                        self.repository.save,
                        "ml_settings",
                        "default",
                        {"active_model_id": trained["id"]},
                    )
                    job["model_id"] = trained["id"]
                    job["progress"] = job["total"]
                    job["status"], job["message"] = (
                        "COMPLETED",
                        "Model je natrénovaný a připravený pro nové simulace.",
                    )
            else:
                job["status"], job["message"] = "COMPLETED", "Párové porovnání je dokončené."
        except Exception as exc:
            job["status"], job["error"] = "FAILED", str(exc)
            job["message"] = "Úlohu se nepodařilo dokončit. Již nasbíraná data zůstala uložená."
        finally:
            await self.persist(job)

    async def close(self) -> None:
        for job in self.jobs.values():
            if job["status"] == "RUNNING":
                job["status"] = "CANCELLING"
        if self.tasks:
            await asyncio.gather(*self.tasks, return_exceptions=True)
        self.pool.shutdown(wait=False, cancel_futures=True)
