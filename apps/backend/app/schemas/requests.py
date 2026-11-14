from typing import Literal

from pydantic import Field

from app.domain.models import AlgorithmConfig, Finite, Model, Point, Scenario


class CreateSimulation(Model):
    scenario_id: str | None = None
    scenario: Scenario | None = None
    config: AlgorithmConfig | None = None
    replace_id: str | None = None


class SpeedRequest(Model):
    speed: Finite = Field(ge=0.25, le=16)


class ObstacleRequest(Model):
    position: Point
    remove: bool = False


class AvailabilityRequest(Model):
    available: bool


class ExperimentRequest(Model):
    name: str = Field(default="Algorithm comparison", min_length=1, max_length=120)
    scenario_id: str = "demo-small"
    mode: Literal["transport", "mapf"] = "mapf"
    benchmark: Literal["A", "B", "C", "D", "E", "F"] = "A"
    algorithms: list[Literal["astar", "prioritized", "cbs", "adaptive"]] = Field(
        default=["astar", "prioritized", "cbs", "adaptive"],
        min_length=1,
        max_length=4,
    )
    schedulers: list[Literal["nearest", "priority", "hungarian"]] = Field(
        default=["priority"], min_length=1, max_length=3
    )
    robot_counts: list[int] = Field(default_factory=lambda: [4], min_length=1, max_length=5)
    task_count: int = Field(default=8, ge=1, le=100)
    repetitions: int = Field(default=2, ge=1, le=10)
    max_run_seconds: Finite = Field(default=30, ge=1, le=120)
    max_ticks: int = Field(default=500, ge=1, le=3000)
    seed: int = Field(default=42, ge=0, le=2**32 - 11)
    config: AlgorithmConfig = Field(default_factory=AlgorithmConfig)
