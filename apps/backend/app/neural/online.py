"""Continue training the deployed MLP from the outcomes of neural runs."""

import logging
from collections import deque
from dataclasses import dataclass
from threading import Lock
from typing import Any

import numpy as np
from sqlalchemy.exc import SQLAlchemyError

from app.neural.policy import KINDS, NeuralPolicy, load_policy, overview, weight_id
from app.persistence.database import Repository

UPDATE_TICKS = 64
MAX_EXPERIENCES = 256
REPLAY_LAYOUTS = 16
MOTION_FEATURE = KINDS.index("move")
SHARED_TRAINING_KIND = "neural_shared_training"
SHARED_TRAINING_KEY = "fleet-v1"


@dataclass(frozen=True)
class Experience:
    values: tuple[float, ...]
    reward: float


def remember_layout(
    replay: dict[str, list[Experience]], layout: str, samples: list[Experience]
) -> None:
    recent = replay.pop(layout, []) + samples
    motion = [sample for sample in recent if sample.values[MOTION_FEATURE]]
    dispatch = [sample for sample in recent if not sample.values[MOTION_FEATURE]]
    replay[layout] = motion[-32:] + dispatch[-16:]
    if len(replay) > REPLAY_LAYOUTS:
        del replay[next(iter(replay))]


def read_experiences(samples: list[dict[str, Any]]) -> list[Experience]:
    return [Experience(tuple(sample["values"]), sample["reward"]) for sample in samples]


class ExperienceBuffer:
    def __init__(self) -> None:
        self.motion: deque[Experience] = deque(maxlen=MAX_EXPERIENCES)
        self.dispatch: deque[Experience] = deque(maxlen=MAX_EXPERIENCES // 4)
        self.pending: dict[str, tuple[tuple[float, ...], int, float]] = {}

    def drain(self) -> list[Experience]:
        samples = list(self.motion) + list(self.dispatch)
        self.motion.clear()
        self.dispatch.clear()
        return samples

    def dispatch_started(
        self, robot_id: str, values: tuple[float, ...], tick: int, optimistic_ticks: float
    ) -> None:
        self.pending[robot_id] = (values, tick, optimistic_ticks)

    def dispatch_finished(self, robot_id: str, tick: int) -> None:
        if entry := self.pending.pop(robot_id, None):
            values, started, optimistic_ticks = entry
            # Credit successful actions, with less credit for inefficient trips.
            ratio = optimistic_ticks / max(tick - started, 1)
            self.dispatch.append(Experience(values, min(1.0, 0.2 + 0.8 * ratio)))

    def dispatch_failed(self) -> None:
        for values, _, _ in self.pending.values():
            self.dispatch.append(Experience(values, -0.6))
        self.pending.clear()


def update(
    policy: NeuralPolicy, seed: NeuralPolicy, samples: list[Experience], *, rate: float = 0.003
) -> list[dict[str, Any]]:
    """Reward-weighted binary loss on actions with observed outcomes."""
    x = np.asarray([sample.values for sample in samples])
    rewards = np.asarray([sample.reward for sample in samples])
    activations = [x]
    for weights, bias in policy.layers:
        activations.append(np.maximum(activations[-1] @ weights + bias, 0))
    weights, bias = policy.layers[-1]
    logits = activations[-2] @ weights + bias
    probabilities = 1 / (1 + np.exp(-np.clip(logits[:, 0], -40, 40)))
    error = ((probabilities - (rewards > 0)) * np.abs(rewards))[:, None] / len(samples)
    layers = []
    for i in reversed(range(len(policy.layers))):
        weights, bias = policy.layers[i]
        initial_weights, initial_bias = seed.layers[i]
        dw = activations[i].T @ error + 0.015 * (weights - initial_weights)
        db = error.sum(axis=0) + 0.015 * (bias - initial_bias)
        # Keep each update small so a single crowded warehouse cannot overwrite the base policy.
        scale = rate / max(1.0, float(np.linalg.norm(dw) + np.linalg.norm(db)))
        layers.append(
            {"weights": (weights - scale * dw).tolist(), "bias": (bias - scale * db).tolist()}
        )
        if i:
            error = (error @ weights.T) * (activations[i] > 0)
    return list(reversed(layers))


class OnlineLearning:
    """One serialized, durable learner for all live simulations in the app."""

    def __init__(self, repository: Repository):
        self.repository = repository
        self.seed = load_policy()
        self._policy = self.seed
        self.updates = 0
        self.samples = 0
        self.replay: dict[str, list[Experience]] = {}
        self.generated_round = 0
        self.lock = Lock()

    def restore(self, bootstrap: NeuralPolicy | None = None) -> None:
        checkpoint = self.repository.get("neural_policy", "live")
        if checkpoint and checkpoint["initial_model_id"] == self.seed.id:
            if bootstrap is not None and "replay" not in checkpoint:
                self._policy = bootstrap
                return
            self._policy = NeuralPolicy(checkpoint["model"])
            self.updates = checkpoint["updates"]
            self.samples = checkpoint["samples"]
            self.replay = {
                layout: read_experiences(samples)
                for layout, samples in checkpoint.get("replay", {}).items()
            }
            self.generated_round = checkpoint.get("generated_round", 0)
        elif bootstrap is not None:
            self._policy = bootstrap

    def current(self) -> NeuralPolicy:
        with self.lock:
            return self._policy

    def summary(self) -> dict[str, Any]:
        with self.lock:
            return {
                "id": self._policy.id,
                "initial_model_id": self.seed.id,
                "updates": self.updates,
                "learned_samples": self.samples,
                "update_ticks": UPDATE_TICKS,
                "replay_layouts": len(self.replay),
            }

    def overview(self) -> dict[str, Any]:
        base = overview()
        return {**base, **self.summary()}

    def learn(self, samples: list[Experience], layout: str | None = None) -> NeuralPolicy | None:
        with self.lock:
            try:
                replay = self.replay.copy()
                generated_round = self.generated_round
                new_samples = len(samples)
                batch = samples
                if layout is not None:
                    generated = self.repository.get(SHARED_TRAINING_KIND, SHARED_TRAINING_KEY)
                    if generated and generated["round"] > generated_round:
                        generated_round = generated["round"]
                        for item in generated.get("live_experience", []):
                            examples = read_experiences(item["samples"])
                            if examples:
                                remember_layout(replay, item["layout"], examples)
                                new_samples += len(examples)
                    remember_layout(replay, layout, samples)
                    batch = [sample for examples in replay.values() for sample in examples]
                layers = update(self._policy, self.seed, batch, rate=0.001 if layout else 0.003)
                artifact = {
                    **self._policy.artifact,
                    "id": weight_id(
                        layers,
                        self._policy.artifact.get("passage_weights"),
                        self._policy.waiting_weights,
                        self._policy.charging_weights,
                        self._policy.coordination_weights,
                    ),
                    "layers": layers,
                }
                policy = NeuralPolicy(artifact)
                self.repository.save(
                    "neural_policy",
                    "live",
                    {
                        "initial_model_id": self.seed.id,
                        "updates": self.updates + 1,
                        "samples": self.samples + new_samples,
                        "model": artifact,
                        "replay": {
                            key: [
                                {"values": sample.values, "reward": sample.reward}
                                for sample in examples
                            ]
                            for key, examples in replay.items()
                        },
                        "generated_round": generated_round,
                    },
                )
            except SQLAlchemyError:
                logging.getLogger("warehouse").warning("Neural checkpoint save failed; will retry")
                return None
            self._policy = policy
            self.updates += 1
            self.samples += new_samples
            self.replay = replay
            self.generated_round = generated_round
            return policy
