import asyncio
import json
import logging
from collections import deque
from uuid import uuid4

from sqlalchemy.exc import SQLAlchemyError

from app.domain.models import Point, Scenario, SimulationState, TrainingAttempt, TrainingLoop
from app.neural.online import UPDATE_TICKS, Experience, ExperienceBuffer, OnlineLearning
from app.persistence.database import Repository
from app.simulation.engine import Engine

TERMINAL = {"COMPLETED", "FAILED", "STOPPED"}
TRAINING_TICK_LIMIT = 4000
TRAINING_RESTART_DELAY = 2.0
SNAPSHOT_INTERVAL = 0.05


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
        self.training_updates = 0
        self.restart_training_at: float | None = None
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
        self.motion_frames: deque[tuple[int, list[Point]]] = deque(maxlen=32)
        self.last_snapshot_at = 0.0
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
        if state.training_loop and state.training_loop.active:
            self.training_updates += 1
        self.update_learning_status()

    def reset_engine(self, training: TrainingLoop | None = None) -> None:
        previous = self.engine.state
        initial = self.engine.initial.model_copy(deep=True)
        initial.config.neural_model_id = None
        self.engine = Engine(
            initial, previous.id, policy=self.online.current(), experience=ExperienceBuffer()
        )
        self.last_update_tick = self.training_updates = 0
        self.motion_frames.clear()
        self.restart_training_at = None
        self.update_learning_status()
        state = self.engine.state
        state.sequence, state.speed = previous.sequence, previous.speed
        state.training_loop = training
        self.persisted = self.persistence_warning = False
        self.engine.emit("SIMULATION_RESET", "Scenario reset to its initial state")

    def start_run(self) -> None:
        self.engine.state.status = "RUNNING"
        self.engine.emit("SIMULATION_STARTED", "Simulation running")

    def record_training_result(self) -> None:
        state = self.engine.state
        training = state.training_loop
        if not training or not training.active or self.retry_samples:
            return
        if state.status != "COMPLETED" and state.status != "FAILED":
            return
        if training.finished_attempts == training.attempt:
            return
        completed = state.metrics.completed_tasks
        training.last_result = TrainingAttempt(
            status=state.status,
            ticks=state.tick,
            completed_tasks=completed,
            model_updates=self.training_updates,
            error=state.error,
        )
        training.finished_attempts = training.attempt
        training.best_completed_tasks = max(training.best_completed_tasks, completed)
        self.restart_training_at = asyncio.get_running_loop().time() + TRAINING_RESTART_DELAY

    async def publish(self) -> dict[str, object]:
        self.engine.state.sequence += 1
        # Keep the manual run archive independent of repeated training attempts.
        if (
            self.engine.state.status in TERMINAL
            and not self.persisted
            and self.engine.state.training_loop is None
        ):
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
        self.last_snapshot_at = asyncio.get_running_loop().time()
        payload = self.snapshot()
        for client in self.clients:
            if client.full():
                client.get_nowait()
            client.put_nowait(payload)
        return payload

    def snapshot(self) -> dict[str, object]:
        state = self.engine.state
        payload = state.model_dump(mode="json")
        if self.motion_frames:
            payload["view_motion"] = {
                "episode": self.engine.episode_id,
                "frames": list(self.motion_frames),
            }
        return {
            "version": 1,
            "type": "STATE_SNAPSHOT",
            "sequence": state.sequence,
            "state": payload,
        }

    async def step(self) -> None:
        state = self.engine.state
        before = state.tick
        await asyncio.to_thread(self.engine.step)
        if state.tick > before:
            self.motion_frames.append((state.tick, [r.position for r in state.robots]))

    async def tick_loop(self) -> None:
        clock = asyncio.get_running_loop().time
        try:
            while True:
                async with self.lock:
                    started = clock()
                    state = self.engine.state
                    training = state.training_loop
                    running = state.status == "RUNNING"
                    if running:
                        try:
                            await self.step()
                        except Exception as exc:
                            self.engine.fail(f"Simulation error: {type(exc).__name__}: {exc}")
                        if (
                            training
                            and training.active
                            and state.status == "RUNNING"
                            and state.tick >= TRAINING_TICK_LIMIT
                        ):
                            self.engine.fail("Training attempt reached its tick limit.")
                        terminal = state.status in TERMINAL
                        await self.learn(flush=terminal)
                        self.record_training_result()
                        if terminal or (
                            self.clients and clock() - self.last_snapshot_at >= SNAPSHOT_INTERVAL
                        ):
                            await self.publish()
                    elif (
                        training
                        and training.active
                        and self.restart_training_at is not None
                        and clock() >= self.restart_training_at
                    ):
                        training.attempt += 1
                        self.reset_engine(training)
                        self.start_run()
                        await self.publish()
                    elif self.retry_samples or (
                        state.status in TERMINAL and not self.persisted and training is None
                    ):
                        await self.learn(flush=True)
                        self.record_training_result()
                        await self.publish()
                    state = self.engine.state
                    if self.persistence_warning or self.retry_samples:
                        delay = 5.0
                    elif state.status == "RUNNING":
                        # Speed is the target period, including the work to execute the step.
                        elapsed = clock() - started if running else 0.0
                        delay = max(0.0, 0.35 / state.speed - elapsed)
                    else:
                        delay = SNAPSHOT_INTERVAL
                await asyncio.sleep(delay)
        except asyncio.CancelledError:
            return

    async def control(self, action: str) -> SimulationState:
        async with self.lock:
            state = self.engine.state
            training = state.training_loop
            if action == "training-start":
                if not training or not training.active:
                    await self.learn(flush=True)
                    if self.retry_samples:
                        raise ValueError("Training progress could not be saved. Try again.")
                    self.reset_engine(TrainingLoop())
                    self.start_run()
            elif action == "reset":
                await self.learn(flush=True)
                self.reset_engine()
            elif action == "start":
                if state.status in TERMINAL:
                    raise ValueError("Reset a finished run before starting it again")
                if training and not training.active:
                    state.training_loop = None
                self.start_run()
            elif action in {"pause", "training-stop"}:
                if training and training.active:
                    await self.learn(flush=True)
                    self.record_training_result()
                    training.active = False
                    self.restart_training_at = None
                if state.status == "RUNNING" and (action == "pause" or training is not None):
                    state.status = "PAUSED"
                    self.engine.emit("SIMULATION_PAUSED", "Simulation paused")
            elif action == "step":
                if state.status == "RUNNING":
                    raise ValueError("Pause before single stepping")
                if state.status in TERMINAL:
                    raise ValueError("Reset a finished simulation before stepping")
                state.training_loop = None
                state.status = "PAUSED"
                await self.step()
                await self.learn(flush=state.status in {"COMPLETED", "FAILED"})
            elif action == "stop":
                if training:
                    training.active = False
                    self.restart_training_at = None
                state.status = "STOPPED"
                self.engine.emit("SIMULATION_STOPPED", "Simulation stopped by user")
                await self.learn(flush=True)
            else:
                raise ValueError("Unknown simulation action")
            await self.publish()
            return self.engine.state.model_copy(deep=True)
