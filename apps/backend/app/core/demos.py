import random

from app.domain.models import Cell, CellType, Robot, Scenario, TransportTask, Warehouse


def demo(
    size: str = "small",
    seed: int = 42,
    robot_count: int | None = None,
    task_count: int | None = None,
) -> Scenario:
    width, height, count, jobs = {
        "small": (20, 14, 4, 12),
        "medium": (28, 20, 6, 24),
        "large": (40, 28, 10, 40),
    }[size]
    count, jobs = robot_count or count, task_count if task_count is not None else jobs
    cells: dict[tuple[int, int], CellType] = {}
    for x in range(4, width - 3, 4):
        for y in range(3, height - 4):
            if y != height // 2:
                cells[x, y] = CellType.SHELF
                cells[x + 1, y] = CellType.SHELF
    stations = list(range(2, height - 3, 3))
    for y in stations:
        cells[1, y] = CellType.PICKUP
        cells[width - 2, y] = CellType.DROPOFF
    robots = []
    for i in range(count):
        home = (1 + i % (width - 2), height - 2 - i // (width - 2))
        cells[home] = CellType.CHARGER
        robots.append(Robot(id=f"R-{i + 1:02}", name=f"Atlas {i + 1:02}", position=home, home=home))
    rng = random.Random(seed)
    tasks = [
        TransportTask(
            id=f"T-{i + 1:03}",
            pickup=(1, rng.choice(stations)),
            dropoff=(width - 2, rng.choice(stations)),
            priority=rng.randint(1, 5),
        )
        for i in range(jobs)
    ]
    warehouse = Warehouse(
        id=f"warehouse-{size}",
        name=f"{size.title()} Warehouse",
        width=width,
        height=height,
        cells=[Cell(x=x, y=y, type=k) for (x, y), k in sorted(cells.items())],
    )
    return Scenario(
        id=f"demo-{size}",
        name=f"{size.title()} Warehouse",
        warehouse=warehouse,
        robots=robots,
        tasks=tasks,
        seed=seed,
    )
