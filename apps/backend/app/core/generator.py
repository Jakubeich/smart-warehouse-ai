"""Seeded, connected warehouse layouts; geometry generation is procedural, not ML."""

import hashlib
import json
import random
from collections import deque
from typing import Literal

from pydantic import Field

from app.domain.grid import Grid
from app.domain.models import (
    Cell,
    CellType,
    Model,
    Point,
    Robot,
    Scenario,
    TransportTask,
    Warehouse,
)

GENERATOR_VERSION = 2


class GeneratorRequest(Model):
    name: str = Field(default="Generovaný sklad", min_length=1, max_length=100)
    width: int = Field(default=20, ge=12, le=64)
    height: int = Field(default=16, ge=10, le=64)
    density: float = Field(default=0.25, ge=0, le=0.4, allow_inf_nan=False)
    layout: Literal["aisles", "islands", "mixed"] = "mixed"
    robot_count: int = Field(default=4, ge=1, le=32)
    task_count: int = Field(default=20, ge=1, le=200)
    seed: int = Field(default=42, ge=0, le=2**32 - 1)
    bottlenecks: bool = False
    passage_width: int = Field(default=1, ge=1, le=3)
    passage_count: int = Field(default=2, ge=1, le=3)
    traffic: Literal["one_way", "bidirectional"] = "one_way"


def layout_key(warehouse: Warehouse) -> str:
    physical = [
        warehouse.width,
        warehouse.height,
        warehouse.cell_size,
        sorted((c.x, c.y, c.type.value) for c in warehouse.cells if c.type != CellType.FLOOR),
    ]
    return hashlib.sha256(json.dumps(physical).encode()).hexdigest()[:24]


def generate(request: GeneratorRequest) -> Scenario:
    rng = random.Random(request.seed)
    w, h = request.width, request.height
    blocked: set[Point] = set()
    target = round(w * h * request.density)
    # Each rectangle is separated by open corridors. The central cross-aisle and
    # two-cell perimeter always remain open, including all station approaches.
    modules: list[set[Point]] = []
    for x in range(rng.choice([2, 3]), w - 3, 4):
        for y in range(rng.choice([2, 3]), h - 4, 5 if request.layout == "aisles" else 4):
            height = 3 if request.layout == "aisles" else 2
            if request.layout == "mixed":
                height = rng.choice([1, 2, 3])
            module = {
                (a, b)
                for a in range(x, min(x + 2, w - 3))
                for b in range(y, min(y + height, h - 4))
                if b != h // 2
            }
            if module:
                modules.append(module)
    rng.shuffle(modules)
    # Reserve a random empty module, even if requested density exceeds what fits
    # with the protected corridors. Actual coverage is reported in metadata.
    if len(modules) > 2:
        modules.pop()
    for module in modules:
        if len(blocked) >= target:
            break
        blocked |= module
    cells = {p: CellType.SHELF for p in blocked}
    passages: list[int] = []
    if request.bottlenecks:
        # A two-cell-thick partition reaches both boundaries: no perimeter bypass.
        # Clear flanking aisles so shelves cannot isolate pockets at the partition.
        count, width = request.passage_count, request.passage_width
        span = h - 4
        if span < count * width + count - 1:
            raise ValueError("Průjezdy se nevejdou. Zvětšete výšku nebo snižte jejich počet/šířku.")
        for i in range(count):
            low = 1 + i * (span + 1) // count
            high = 1 + (i + 1) * (span + 1) // count - 1
            start = rng.randint(low, high - width)
            passages.extend(range(start, start + width))
        for x in range(w // 2 - 2, w // 2 + 2):
            for y in range(h):
                cells.pop((x, y), None)
                if x in {w // 2 - 1, w // 2} and y not in passages:
                    cells[x, y] = CellType.WALL
    station_rows = list(range(2, h - 3, 3))
    pickups, dropoffs = [(1, y) for y in station_rows], [(w - 2, y) for y in station_rows]
    for p in pickups:
        cells[p] = CellType.PICKUP
    for p in dropoffs:
        cells[p] = CellType.DROPOFF
    reverse_pickups = [(w - 2, y + 1) for y in station_rows]
    reverse_dropoffs = [(1, y + 1) for y in station_rows]
    if request.traffic == "bidirectional":
        for p in reverse_pickups:
            cells[p] = CellType.PICKUP
        for p in reverse_dropoffs:
            cells[p] = CellType.DROPOFF
    homes = [(x, y) for y in (h - 2, h - 3) for x in range(1, w - 1) if (x, y) not in cells]
    if request.robot_count > len(homes):
        raise ValueError("Pro tento počet robotů zvětšete rozměry skladu.")
    rng.shuffle(homes)
    if request.bottlenecks or request.traffic == "bidirectional":
        left = [p for p in homes if p[0] < w // 2]
        right = [p for p in homes if p[0] >= w // 2]
        homes = [
            p
            for i in range(max(len(left), len(right)))
            for side in (left, right)
            if i < len(side)
            for p in [side[i]]
        ]
    robots = []
    for i, home in enumerate(homes[: request.robot_count]):
        cells[home] = CellType.CHARGER
        # Capacity permits the full supported warehouse extent with a return reserve.
        robots.append(
            Robot(
                id=f"R-{i + 1:02}",
                name=f"Robot {i + 1:02}",
                position=home,
                home=home,
                battery_capacity=200,
                battery=200,
            )
        )
    key = hashlib.sha256(json.dumps(request.model_dump(), sort_keys=True).encode()).hexdigest()[:16]
    warehouse = Warehouse(
        id=f"generated-map-{key}",
        name=request.name,
        width=w,
        height=h,
        cells=[Cell(x=x, y=y, type=t) for (x, y), t in sorted(cells.items())],
        metadata={
            "generator_version": str(GENERATOR_VERSION),
            "generator": request.model_dump_json(),
            "shelf_coverage": str(
                round(sum(t == CellType.SHELF for t in cells.values()) / (w * h), 4)
            ),
            "passage_rows": json.dumps(passages),
        },
    )
    grid = Grid(warehouse)
    reached = {robots[0].position}
    queue = deque(reached)
    while queue:
        for point in grid.neighbors(queue.popleft()):
            if point not in reached:
                reached.add(point)
                queue.append(point)
    if len(reached) != w * h - len(grid.blocked):
        raise ValueError("Generátor nevytvořil souvislou mapu. Zvolte jiný seed.")
    tasks = [
        TransportTask(
            id=f"T-{i + 1:03}",
            pickup=rng.choice(
                reverse_pickups if request.traffic == "bidirectional" and i % 2 else pickups
            ),
            dropoff=rng.choice(
                reverse_dropoffs if request.traffic == "bidirectional" and i % 2 else dropoffs
            ),
            priority=rng.randint(1, 5),
            load_duration=rng.randint(1, 4),
            unload_duration=rng.randint(1, 4),
            payload_weight=rng.choice([5, 10, 20, 35]),
        )
        for i in range(request.task_count)
    ]
    return Scenario(
        id=f"generated-{key}",
        name=request.name,
        warehouse=warehouse,
        robots=robots,
        tasks=tasks,
        seed=request.seed,
    )
