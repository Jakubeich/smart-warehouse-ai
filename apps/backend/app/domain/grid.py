from bisect import bisect_left
from dataclasses import dataclass
from functools import cached_property

from app.domain.models import CellType, Point, Warehouse


def manhattan(a: Point, b: Point) -> int:
    return abs(a[0] - b[0]) + abs(a[1] - b[1])


@dataclass
class DistanceField:
    reached: list[int]
    frontier: int


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
        self._stride = self.width + 1
        self._distances: dict[Point, DistanceField] = {}
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

    def _bit(self, point: Point) -> int:
        return 1 << (point[1] * self._stride + point[0])

    @cached_property
    def _passable(self) -> int:
        # One unused bit per row prevents horizontal shifts from wrapping.
        rows = sum(((1 << self.width) - 1) << (y * self._stride) for y in range(self.height))
        blocked = sum(
            self._bit((x, y))
            for x, y in self.blocked
            if 0 <= x < self.width and 0 <= y < self.height
        )
        return rows & ~blocked

    def distance(self, start: Point, goal: Point) -> int | None:
        if not self.walkable(start) or not self.walkable(goal):
            return None
        start_bit = self._bit(start)
        field = self._distances.get(goal)
        if field is None:
            goal_bit = self._bit(goal)
            field = self._distances[goal] = DistanceField([goal_bit], goal_bit)
        if field.reached[-1] & start_bit:
            return bisect_left(field.reached, True, key=lambda layer: bool(layer & start_bit))

        # Grow the reverse BFS by whole layers, only as far as the query needs.
        stride, passable = self._stride, self._passable
        while frontier := field.frontier:
            adjacent = (frontier << 1) | (frontier >> 1) | (frontier << stride) | (frontier >> stride)
            field.frontier = adjacent & passable & ~field.reached[-1]
            if field.frontier:
                field.reached.append(field.reached[-1] | field.frontier)
                if field.frontier & start_bit:
                    return len(field.reached) - 1
        return None

    def shortest_path(self, start: Point, goal: Point) -> list[Point]:
        """Deterministic geometric route, reusing the reverse BFS distance field."""
        distance = self.distance(start, goal)
        if distance is None:
            return []
        route = [start]
        reached = self._distances[goal].reached
        while distance:
            closer = reached[distance - 1]
            route.append(next(p for p in self.neighbors(route[-1]) if closer & self._bit(p)))
            distance -= 1
        return route
