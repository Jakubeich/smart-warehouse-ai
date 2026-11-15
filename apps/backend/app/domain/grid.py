from collections import deque

from app.domain.models import CellType, Point, Warehouse


def manhattan(a: Point, b: Point) -> int:
    return abs(a[0] - b[0]) + abs(a[1] - b[1])


class Grid:
    def __init__(self, warehouse: Warehouse, obstacles: set[Point] | None = None):
        self.width = warehouse.width
        self.height = warehouse.height
        self.cells = {(c.x, c.y): c.type for c in warehouse.cells}
        self.chargers = tuple(p for p, kind in self.cells.items() if kind == CellType.CHARGER)
        self.blocked = {
            p
            for p, kind in self.cells.items()
            if kind in {CellType.WALL, CellType.SHELF, CellType.OBSTACLE}
        }
        self.blocked |= obstacles or set()
        self._distances: dict[Point, dict[Point, int]] = {}
        self._neighbors: dict[Point, tuple[Point, ...]] = {}

    def kind(self, p: Point) -> CellType:
        return self.cells.get(p, CellType.FLOOR)

    def walkable(self, p: Point) -> bool:
        return 0 <= p[0] < self.width and 0 <= p[1] < self.height and p not in self.blocked

    def neighbors(self, p: Point) -> tuple[Point, ...]:
        if p not in self._neighbors:
            x, y = p
            self._neighbors[p] = tuple(
                q for q in ((x + 1, y), (x, y + 1), (x - 1, y), (x, y - 1)) if self.walkable(q)
            )
        return self._neighbors[p]

    def distance(self, start: Point, goal: Point) -> int | None:
        if not self.walkable(start) or not self.walkable(goal):
            return None
        if goal not in self._distances:
            distances = {goal: 0}
            queue = deque([goal])
            while queue:
                p = queue.popleft()
                for q in self.neighbors(p):
                    if q not in distances:
                        distances[q] = distances[p] + 1
                        queue.append(q)
            self._distances[goal] = distances
        return self._distances[goal].get(start)

    def shortest_path(self, start: Point, goal: Point) -> list[Point]:
        """Deterministic geometric route, reusing the reverse BFS distance field."""
        distance = self.distance(start, goal)
        if distance is None:
            return []
        route = [start]
        field = self._distances[goal]
        while distance:
            route.append(next(p for p in self.neighbors(route[-1]) if field.get(p) == distance - 1))
            distance -= 1
        return route
