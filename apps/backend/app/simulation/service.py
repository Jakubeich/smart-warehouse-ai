import asyncio
import json
import logging
from uuid import uuid4

from sqlalchemy.exc import SQLAlchemyError

from app.domain.models import Scenario, SimulationState
from app.neural.online import UPDATE_TICKS, Experience, ExperienceBuffer, OnlineLearning
from app.persistence.database import Repository
from app.simulation.engine import Engine


class SimulationSession:
    def __init__(
        self,
        scenario: Scenario,
        repository: Repository,
        online: OnlineLearning,
    ):
        self.online = online
        self.retry_samples: list[Experience] = []
        self.last_update_tick = 0
        scenario = scenario.model_copy(deep=True)
        scenario.config.control = "neural"
        scenario.config.neural_model_id = None
        scenario.config.ml_model_id = None
        self.engine = Engine(
            scenario, str(uuid4()), policy=online.current(), experience=ExperienceBuffer()
        )
        self.update_learning_status()
        self.repository = repository
        self.lock = asyncio.Lock()
        self.closed = asyncio.Event()
        self.clients: set[asyncio.Queue[dict[str, object]]] = set()
        self.task: asyncio.Task[None] | None = None
        self.persisted = False
        self.persistence_warning = False

    def update_learning_status(self) -> None:
        summary = self.online.summary()
        self.engine.state.neural_updates = summary["updates"]
        self.engine.state.neural_learned_samples = summary["learned_samples"]

    async def learn(self, *, flush: bool = False) -> None:
        experience = self.engine.experience
        assert experience is not None
        state = self.engine.state
        if not flush and state.tick - self.last_update_tick < UPDATE_TICKS:
            return
        self.last_update_tick = state.tick
        samples = (self.retry_samples + experience.drain())[-640:]
        if not samples:
            return
        policy = await asyncio.to_thread(self.online.learn, samples)
        if not policy:
            self.retry_samples = samples
            return
        self.retry_samples = []
        self.engine.policy = policy
        state.config.neural_model_id = policy.id
        self.update_learning_status()

    async def publish(self) -> dict[str, object]:
        self.engine.state.sequence += 1
        if self.engine.state.status in {"COMPLETED", "FAILED", "STOPPED"} and not self.persisted:
            try:
                await asyncio.to_thread(
                    self.repository.save,
                    "run",
                    self.engine.state.id,
                    self.engine.state.model_dump(mode="json"),
                )
                self.persisted = True
                if self.persistence_warning:
                    self.engine.emit("PERSISTENCE_RECOVERED", "Run saved after database recovery")
                    self.persistence_warning = False
            except SQLAlchemyError as exc:
                logging.getLogger("warehouse").error(
                    json.dumps(
                        {
                            "event": "run_save_failed",
                            "simulation_id": self.engine.state.id,
                            "type": type(exc).__name__,
                        }
                    )
                )
                if not self.persistence_warning:
                    self.engine.emit(
                        "SIMULATION_ERROR",
                        "Run could not be saved. Export the snapshot; database save will retry.",
                    )
                    self.persistence_warning = True
        payload: dict[str, object] = {
            "version": 1,
            "type": "STATE_SNAPSHOT",
            "sequence": self.engine.state.sequence,
            "state": self.engine.state.model_dump(mode="json"),
        }
        for client in self.clients:
            if client.full():
                client.get_nowait()
            client.put_nowait(payload)
        return payload

    async def tick_loop(self) -> None:
        try:
            while True:
                async with self.lock:
                    if self.engine.state.status == "RUNNING":
                        try:
                            await asyncio.to_thread(self.engine.step)
                        except Exception as exc:
                            self.engine.fail(f"Simulation error: {type(exc).__name__}: {exc}")
                        await self.learn(flush=self.engine.state.status in {"COMPLETED", "FAILED"})
                        await self.publish()
                    elif self.engine.state.status in {"COMPLETED", "FAILED", "STOPPED"} and (
                        not self.persisted or self.retry_samples
                    ):
                        await self.learn(flush=True)
                        await self.publish()
                    delay = (
                        5
                        if self.persistence_warning or self.retry_samples
                        else 0.35 / self.engine.state.speed
                    )
                await asyncio.sleep(delay)
        except asyncio.CancelledError:
            return

    async def control(self, action: str) -> SimulationState:
        async with self.lock:
            state = self.engine.state
            if action == "reset":
                sequence = state.sequence
                speed = state.speed
                await self.learn(flush=True)
                initial = self.engine.initial.model_copy(deep=True)
                initial.config.neural_model_id = None
                self.engine = Engine(
                    initial, state.id, policy=self.online.current(), experience=ExperienceBuffer()
                )
                self.last_update_tick = 0
                self.update_learning_status()
                self.engine.state.sequence, self.engine.state.speed = sequence, speed
                self.persisted = False
                self.persistence_warning = False
                self.engine.emit("SIMULATION_RESET", "Scenario reset to its initial state")
            elif action == "start":
                if state.status in {"COMPLETED", "FAILED", "STOPPED"}:
                    raise ValueError("Reset a finished run before starting it again")
                state.status = "RUNNING"
                self.engine.emit("SIMULATION_STARTED", "Simulation running")
            elif action == "pause":
                if state.status == "RUNNING":
                    state.status = "PAUSED"
                    self.engine.emit("SIMULATION_PAUSED", "Simulation paused")
            elif action == "step":
                if state.status == "RUNNING":
                    raise ValueError("Pause before single stepping")
                if state.status in {"FAILED", "COMPLETED", "STOPPED"}:
                    raise ValueError("Reset a finished simulation before stepping")
                state.status = "PAUSED"
                await asyncio.to_thread(self.engine.step)
                await self.learn(flush=state.status in {"COMPLETED", "FAILED"})
            elif action == "stop":
                state.status = "STOPPED"
                self.engine.emit("SIMULATION_STOPPED", "Simulation stopped by user")
                await self.learn(flush=True)
            else:
                raise ValueError("Unknown simulation action")
            await self.publish()
            return self.engine.state.model_copy(deep=True)
