import asyncio
import csv
import io
import json
import logging
from collections.abc import AsyncIterator, Awaitable, Callable
from contextlib import asynccontextmanager
from typing import Annotated, Any

import anyio
from fastapi import FastAPI, HTTPException, Query, Request, WebSocket, WebSocketDisconnect
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse, Response
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError

from app.core.demos import demo
from app.core.generator import GeneratorRequest, generate
from app.domain.models import Scenario, SimulationState, TransportTask, Warehouse
from app.experiments.service import Experiments
from app.learning.service import Learning, LearningRequest
from app.neural.online import OnlineLearning
from app.neural.shared import shared_policy, shared_summary
from app.persistence.database import Repository
from app.schemas.requests import (
    AvailabilityRequest,
    CreateSimulation,
    ExperimentRequest,
    ObstacleRequest,
    SpeedRequest,
)
from app.simulation.service import SimulationSession

logger = logging.getLogger("warehouse")
logging.basicConfig(level=logging.INFO, format="%(message)s")


def create_app(database: Repository | None = None) -> FastAPI:
    repository = database or Repository()
    sessions: dict[str, SimulationSession] = {}
    session_changes = asyncio.Lock()
    experiments = Experiments(repository)
    learning = Learning(repository)
    online = OnlineLearning(repository)

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        await asyncio.to_thread(lambda: online.restore(shared_policy(repository)))
        # Persisted RUNNING jobs lost their process at restart; never pretend they survived.
        for job in await asyncio.to_thread(repository.list, "experiment"):
            if job["status"] == "RUNNING":
                job["status"] = "INTERRUPTED"
                await asyncio.to_thread(repository.save, "experiment", job["id"], job)
        for job in await asyncio.to_thread(repository.list, "ml_job"):
            if job["status"] in {"RUNNING", "CANCELLING"}:
                job["status"], job["message"] = (
                    "INTERRUPTED",
                    "Výpočet byl přerušen restartem serveru.",
                )
                await asyncio.to_thread(repository.save, "ml_job", job["id"], job)
        yield
        for session in sessions.values():
            async with session.lock:
                if session.task:
                    session.task.cancel()
                await session.learn(flush=True)
        await asyncio.gather(*(s.task for s in sessions.values() if s.task), return_exceptions=True)
        await experiments.close()
        await learning.close()
        repository.engine.dispose()

    app = FastAPI(title="Smart Warehouse AI", version="0.1.0", lifespan=lifespan)

    @app.middleware("http")
    async def access_log(
        request: Request, call_next: Callable[[Request], Awaitable[Response]]
    ) -> Response:
        response = await call_next(request)
        logger.info(
            json.dumps(
                {
                    "event": "request",
                    "method": request.method,
                    "path": request.url.path,
                    "status": response.status_code,
                }
            )
        )
        return response

    @app.exception_handler(ValueError)
    async def invalid(request: Request, exc: ValueError) -> JSONResponse:
        return JSONResponse(
            status_code=422, content={"error": {"code": "INVALID_INPUT", "message": str(exc)}}
        )

    @app.exception_handler(RequestValidationError)
    async def invalid_payload(request: Request, exc: RequestValidationError) -> JSONResponse:
        return JSONResponse(
            status_code=422, content={"error": {"code": "VALIDATION_ERROR", "message": str(exc)}}
        )

    @app.exception_handler(HTTPException)
    async def http_error(request: Request, exc: HTTPException) -> JSONResponse:
        return JSONResponse(
            status_code=exc.status_code,
            content={"error": {"code": f"HTTP_{exc.status_code}", "message": str(exc.detail)}},
        )

    @app.exception_handler(SQLAlchemyError)
    async def database_error(request: Request, exc: SQLAlchemyError) -> JSONResponse:
        logger.error(json.dumps({"event": "database_error", "type": type(exc).__name__}))
        return JSONResponse(
            status_code=503,
            content={
                "error": {
                    "code": "DATABASE_UNAVAILABLE",
                    "message": "Database unavailable. Check PostgreSQL and migrations.",
                }
            },
        )

    def session_for(sid: str) -> SimulationSession:
        if sid not in sessions:
            raise HTTPException(
                404, "Active simulation not found. It may have ended at backend restart."
            )
        return sessions[sid]

    async def remove_session(sid: str) -> None:
        session = sessions.get(sid)
        if session is None:
            return
        async with session.lock:
            await session.learn(flush=True)
            if session.retry_samples:
                raise HTTPException(503, "Učení se nepodařilo uložit. Zkuste akci znovu.")
            if session.task:
                session.task.cancel()
            sessions.pop(sid)
            session.closed.set()

    def stored(kind: str, key: str) -> dict[str, Any]:
        data = repository.get(kind, key)
        if data is None:
            raise HTTPException(404, f"{kind.title()} not found")
        return data

    @app.get("/api/health")
    def health() -> dict[str, str]:
        with repository.engine.connect() as connection:
            connection.execute(text("SELECT 1"))
            connection.execute(text("SELECT 1 FROM documents LIMIT 1"))
        return {"status": "ok", "database": "connected", "protocol_version": "1"}

    @app.get("/api/dashboard")
    async def dashboard() -> dict[str, Any]:
        warehouses, scenarios, runs, jobs = await asyncio.gather(
            *(
                asyncio.to_thread(repository.list, k)
                for k in ["warehouse", "scenario", "run", "experiment"]
            )
        )
        return {
            "warehouses": len(warehouses),
            "robots": sum(len(s["robots"]) for s in scenarios),
            "active_simulations": sum(
                s.engine.state.status == "RUNNING" for s in sessions.values()
            ),
            "completed_tasks": sum(r["metrics"]["completed_tasks"] for r in runs),
            "scenarios": scenarios,
            "experiments": jobs[:5],
            "runs": runs[:10],
        }

    @app.post("/api/demos", status_code=201)
    def seed_demos() -> list[dict[str, Any]]:
        result = []
        for size in ["small", "medium", "large"]:
            scene = demo(size)
            existing = repository.get("scenario", scene.id)
            if existing:
                result.append(existing)
                continue
            repository.save(
                "warehouse", scene.warehouse.id, scene.warehouse.model_dump(mode="json")
            )
            result.append(repository.save("scenario", scene.id, scene.model_dump(mode="json")))
        return result

    @app.get("/api/warehouses")
    def warehouses() -> list[dict[str, Any]]:
        return repository.list("warehouse")

    @app.post("/api/warehouses", status_code=201)
    def create_warehouse(warehouse: Warehouse) -> dict[str, Any]:
        if repository.get("warehouse", warehouse.id):
            raise HTTPException(409, "Warehouse ID already exists")
        return repository.save("warehouse", warehouse.id, warehouse.model_dump(mode="json"))

    @app.get("/api/warehouses/{wid}")
    def get_warehouse(wid: str) -> dict[str, Any]:
        return stored("warehouse", wid)

    @app.put("/api/warehouses/{wid}")
    def update_warehouse(wid: str, warehouse: Warehouse) -> dict[str, Any]:
        stored("warehouse", wid)
        if wid != warehouse.id:
            raise ValueError("Path and warehouse IDs differ")
        return repository.save("warehouse", wid, warehouse.model_dump(mode="json"))

    @app.delete("/api/warehouses/{wid}", status_code=204)
    def delete_warehouse(wid: str) -> Response:
        if any(s["warehouse"]["id"] == wid for s in repository.list("scenario")):
            raise HTTPException(409, "Warehouse is referenced by a saved scenario")
        if not repository.delete("warehouse", wid):
            raise HTTPException(404, "Warehouse not found")
        return Response(status_code=204)

    @app.get("/api/scenarios")
    def scenarios() -> list[dict[str, Any]]:
        return repository.list("scenario")

    @app.delete("/api/scenarios", status_code=204)
    def delete_scenario(scenario_id: Annotated[str, Query(min_length=1, max_length=100)]) -> Response:
        repository.delete("scenario", scenario_id)
        return Response(status_code=204)

    @app.post("/api/generator")
    def generate_warehouse(body: GeneratorRequest) -> Scenario:
        return generate(body)

    @app.get("/api/neural")
    def neural_model() -> dict[str, Any]:
        return {**online.overview(), "shared_training": shared_summary(repository)}

    @app.get("/api/learning")
    def learning_overview() -> dict[str, Any]:
        return learning.overview()

    @app.post("/api/learning/jobs", status_code=202)
    async def start_learning(body: LearningRequest) -> dict[str, Any]:
        return await learning.create(body)

    @app.get("/api/learning/jobs/{job_id}")
    def learning_job(job_id: str) -> dict[str, Any]:
        return learning.jobs.get(job_id) or stored("ml_job", job_id)

    @app.post("/api/learning/jobs/{job_id}/cancel")
    async def cancel_learning(job_id: str) -> dict[str, Any]:
        job = learning.cancel(job_id)
        await learning.persist(job)
        return job

    @app.get("/api/learning/models/{model_id}")
    def export_model(model_id: str) -> dict[str, Any]:
        return stored("ml_model", model_id)

    @app.get("/api/scenarios/{sid}")
    def get_scenario(sid: str) -> dict[str, Any]:
        return stored("scenario", sid)

    @app.post("/api/scenarios", status_code=201)
    def save_scenario(scene: Scenario) -> dict[str, Any]:
        if any(r.task_id or r.mode != "IDLE" or r.distance for r in scene.robots):
            raise ValueError("Scenarios must contain initial robot configurations")
        if any(t.status != "PENDING" for t in scene.tasks):
            raise ValueError("Scenarios must contain pending initial tasks")
        repository.save("warehouse", scene.warehouse.id, scene.warehouse.model_dump(mode="json"))
        return repository.save("scenario", scene.id, scene.model_dump(mode="json"))

    @app.post("/api/simulations", status_code=201)
    async def create_simulation(body: CreateSimulation) -> SimulationState:
        if body.scenario is None and body.scenario_id is None:
            raise ValueError("Provide a scenario or scenario_id")
        scene = body.scenario or Scenario.model_validate(
            await asyncio.to_thread(stored, "scenario", body.scenario_id or "")
        )
        if body.config:
            scene.config = body.config.model_copy(
                update={"max_ticks": body.config.max_ticks or scene.config.max_ticks}
            )
        scene = Scenario.model_validate(scene.model_dump())
        async with session_changes:
            if len(sessions) >= 8 and body.replace_id not in sessions:
                raise HTTPException(409, "Limit of 8 active sessions. Delete an old session first.")
            session = SimulationSession(scene, repository, online=online)
            if body.replace_id is not None:
                await remove_session(body.replace_id)
                # Closing the previous run may have flushed new weights.
                session.sync_policy()
            sessions[session.engine.state.id] = session
            session.task = asyncio.create_task(session.tick_loop())
            await session.publish()
            return session.engine.state.model_copy(deep=True)

    @app.get("/api/simulations")
    async def simulations() -> list[dict[str, Any]]:
        return [
            {
                "id": s.engine.state.id,
                "name": s.engine.state.name,
                "status": s.engine.state.status,
                "tick": s.engine.state.tick,
            }
            for s in sessions.values()
        ]

    @app.get("/api/simulations/{sid}")
    async def simulation(sid: str) -> SimulationState:
        session = session_for(sid)
        async with session.lock:
            return session.engine.state.model_copy(deep=True)

    @app.delete("/api/simulations/{sid}", status_code=204)
    async def delete_simulation(sid: str) -> Response:
        async with session_changes:
            await remove_session(sid)
        return Response(status_code=204)

    @app.post("/api/simulations/{sid}/speed")
    async def speed(sid: str, body: SpeedRequest) -> SimulationState:
        session = session_for(sid)
        async with session.lock:
            session.engine.state.speed = body.speed
            await session.publish()
            return session.engine.state.model_copy(deep=True)

    @app.get("/api/simulations/{sid}/robots")
    async def robots(sid: str) -> list[dict[str, Any]]:
        return [r.model_dump(mode="json") for r in (await simulation(sid)).robots]

    @app.post("/api/simulations/{sid}/robots/{rid}/availability")
    async def availability(sid: str, rid: str, body: AvailabilityRequest) -> SimulationState:
        session = session_for(sid)
        async with session.lock:
            session.engine.set_available(rid, body.available)
            await session.publish()
            return session.engine.state.model_copy(deep=True)

    @app.get("/api/simulations/{sid}/tasks")
    async def tasks(sid: str) -> list[dict[str, Any]]:
        return [t.model_dump(mode="json") for t in (await simulation(sid)).tasks]

    @app.post("/api/simulations/{sid}/tasks", status_code=201)
    async def add_task(sid: str, body: TransportTask) -> SimulationState:
        session = session_for(sid)
        async with session.lock:
            session.engine.add_task(body)
            session.persisted = False
            await session.publish()
            return session.engine.state.model_copy(deep=True)

    @app.post("/api/simulations/{sid}/obstacles")
    async def obstacle(sid: str, body: ObstacleRequest) -> SimulationState:
        session = session_for(sid)
        async with session.lock:
            session.engine.obstacle(body.position, body.remove)
            await session.publish()
            return session.engine.state.model_copy(deep=True)

    @app.post("/api/simulations/{sid}/{action}")
    async def control(sid: str, action: str) -> SimulationState:
        return await session_for(sid).control(action)

    @app.websocket("/ws/simulations/{sid}")
    async def websocket(websocket: WebSocket, sid: str) -> None:
        session = sessions.get(sid)
        await websocket.accept()
        if session is None or session.closed.is_set():
            await websocket.close(code=4404, reason="Simulation not found")
            return
        queue: asyncio.Queue[dict[str, object]] = asyncio.Queue(maxsize=1)
        async with session.lock:
            session.clients.add(queue)
            initial = session.snapshot()

        async def sender() -> None:
            await websocket.send_json(initial)
            while True:
                await websocket.send_json(await queue.get())

        async def receiver() -> None:
            while True:
                await websocket.receive_text()

        try:
            async with anyio.create_task_group() as group:
                group.start_soon(sender)

                async def watch_removal() -> None:
                    await session.closed.wait()
                    group.cancel_scope.cancel()

                group.start_soon(watch_removal)
                try:
                    await receiver()
                except (WebSocketDisconnect, RuntimeError):
                    group.cancel_scope.cancel()
            if session.closed.is_set():
                try:
                    await websocket.close(code=4404, reason="Simulation not found")
                except (WebSocketDisconnect, RuntimeError):
                    pass
        finally:
            session.clients.discard(queue)

    @app.get("/api/algorithms")
    def algorithms() -> dict[str, Any]:
        return {
            "planners": ["astar", "prioritized", "cbs", "adaptive"],
            "schedulers": ["nearest", "priority", "hungarian"],
            "semantics": "Discrete 4-connected MAPF, vertex and edge-swap constraints, stay at goal",
        }

    @app.get("/api/experiments")
    def list_experiments() -> list[dict[str, Any]]:
        return repository.list("experiment")

    @app.post("/api/experiments", status_code=202)
    async def create_experiment(body: ExperimentRequest) -> dict[str, Any]:
        scene = Scenario.model_validate(
            await asyncio.to_thread(stored, "scenario", body.scenario_id)
        )
        return experiments.create(body, scene)

    @app.get("/api/experiments/{eid}")
    async def get_experiment(eid: str) -> dict[str, Any]:
        if eid in experiments.jobs:
            return experiments.jobs[eid]
        return await asyncio.to_thread(stored, "experiment", eid)

    @app.post("/api/experiments/{eid}/cancel")
    async def cancel_experiment(eid: str) -> dict[str, Any]:
        job = await get_experiment(eid)
        if job["status"] == "RUNNING":
            job["status"] = "CANCELLED"
            await asyncio.to_thread(repository.save, "experiment", eid, dict(job))
        return job

    @app.get("/api/experiments/{eid}/results")
    async def results(eid: str, format: str = "json") -> Response:
        job = await get_experiment(eid)
        if format == "csv":
            buffer = io.StringIO()
            rows = [
                {
                    **{
                        k: r.get(k)
                        for k in [
                            "algorithm",
                            "scheduler",
                            "seed",
                            "robots",
                            "status",
                            "success",
                            "optimal",
                            "wall_time_ms",
                        ]
                    },
                    **r["metrics"],
                }
                for r in job["results"]
            ]
            if rows:
                writer = csv.DictWriter(buffer, fieldnames=list(rows[0]))
                writer.writeheader()
                writer.writerows(rows)
            return Response(
                buffer.getvalue(),
                media_type="text/csv",
                headers={"Content-Disposition": f'attachment; filename="experiment-{eid}.csv"'},
            )
        return JSONResponse(job)

    @app.get("/api/runs")
    def runs() -> list[dict[str, Any]]:
        return repository.list("run")

    app.state.sessions = sessions
    app.state.repository = repository
    return app


app = create_app()
