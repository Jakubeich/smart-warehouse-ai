from concurrent.futures import ThreadPoolExecutor

import pytest

from app.core.demos import demo
from app.core.generator import GeneratorRequest, generate, layout_key
from app.domain.models import Scenario
from app.neural import shared
from app.neural.policy import FEATURE_COUNT, load_policy, narrow_passage_cells
from app.neural.shared import MapResult, Rollout
from app.neural.training import candidate_from, charging_candidate_from


def test_reuse_matches_real_passage_only_rollout_on_a_map_without_passages() -> None:
    scene = demo("small", robot_count=2, task_count=3)
    parent = load_policy()
    better = tuple(1.0 if i == 9 else 0.0 for i in range(FEATURE_COUNT))
    candidate = candidate_from(parent, [(better, (0.0,) * FEATURE_COUNT)], [], 3)
    assert candidate is not None
    assert not narrow_passage_cells(scene.warehouse)

    baseline = shared.simulate(parent.artifact, scene).result
    independently_run = shared.simulate(candidate.artifact, scene).result
    assert baseline == independently_run
    with ThreadPoolExecutor(1) as pool:
        jobs = shared.compare_batch(pool, parent, candidate, [scene], [baseline])
    assert jobs == [baseline]


@pytest.mark.parametrize("eligible", [False, True])
def test_validation_runs_only_after_a_candidate_qualifies(
    monkeypatch: pytest.MonkeyPatch, eligible: bool
) -> None:
    parent = load_policy()
    candidate = charging_candidate_from(parent, [(10.0, 17.0, False)], 15.0, 0)
    assert candidate is not None
    training = demo("small", robot_count=1, task_count=1)
    validation = generate(GeneratorRequest(seed=926012, robot_count=1, task_count=1))
    generated = []
    evaluated = []

    def batch(seed: int, excluded: set[str], **kwargs: bool) -> list[Scenario]:
        generated.append(seed)
        return [training] if len(generated) == 1 else [validation]

    def rollout(artifact: dict[str, object], scene: Scenario, learn: bool = False) -> Rollout:
        evaluated.append((artifact["id"], scene.id))
        improves = artifact["id"] != parent.id and eligible
        return Rollout(
            MapResult(
                seed=scene.seed,
                layout=layout_key(scene.warehouse),
                tasks=1,
                delivered=1,
                finished=True,
                ticks=10 if artifact["id"] == parent.id else 9 if improves else 11,
                collisions=0,
                depleted=0,
                passage_wait=0,
                longest_passage_wait=0,
            ),
            None,
        )

    monkeypatch.setattr(shared, "generated_batch", batch)
    monkeypatch.setattr(shared, "simulate", rollout)
    monkeypatch.setattr(shared, "proposals", lambda *_: [candidate])
    with ThreadPoolExecutor(1) as pool:
        winner, report, _ = shared.train_round(pool, parent, 0)
    assert (winner is candidate) == eligible
    assert len(generated) == (2 if eligible else 1)
    assert len(evaluated) == (4 if eligible else 2)
    assert bool(report["validation_baseline"]) == eligible
