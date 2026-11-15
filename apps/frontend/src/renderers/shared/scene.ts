import type { Point, Robot, Simulation, Warehouse } from "@/types/domain";
export type VisualType =
  | "RobotVisual"
  | "ShelfVisual"
  | "WallVisual"
  | "FloorVisual"
  | "PickupStationVisual"
  | "DropoffStationVisual"
  | "ChargingStationVisual"
  | "PalletVisual";
export interface VisualEntity {
  id: string;
  type: VisualType;
  position: Point;
  orientation: number;
  assetId: string;
  metadata: Record<string, string | number>;
}
export interface SceneFrame {
  warehouse: Warehouse;
  robots: Robot[];
  simulation?: Simulation;
  selectedRobot?: string | null;
  hover?: Point | null;
}
export interface WarehouseViewProps {
  frame: SceneFrame;
  onCell?: (point: Point) => void;
  onHover?: (point: Point | null) => void;
  onSelect?: (id: string) => void;
  editing?: boolean;
  paintDrag?: boolean;
}

/** Models face +X; grid +Y maps to world +Z. */
export const worldYaw = (orientation: number) => (-orientation * Math.PI) / 180;

/** Only interpolate adjacent authoritative ticks, never resets or missed updates. */
export function canInterpolate(
  previous: { run: string; tick: number; position: Point },
  next: { run: string; tick: number; position: Point },
) {
  return (
    previous.run === next.run &&
    next.tick === previous.tick + 1 &&
    Math.abs(next.position[0] - previous.position[0]) +
      Math.abs(next.position[1] - previous.position[1]) <=
      1
  );
}
export type RobotPose = {
  run: string;
  tick: number;
  position: Point;
  episode?: string;
};

/** Rebuild the real route between snapshots, including turns that happened between them. */
export function motionPath(
  previous: RobotPose | undefined,
  next: RobotPose,
  motion: Simulation["view_motion"],
  robotIndex: number,
): Point[] {
  if (
    !previous ||
    previous.run !== next.run ||
    previous.tick >= next.tick ||
    (previous.episode && next.episode && previous.episode !== next.episode)
  )
    return [next.position];

  if (motion?.frames.length) {
    const first = motion.frames[0][0];
    const path = [previous.position];
    for (let tick = previous.tick + 1; tick <= next.tick; tick++) {
      const frame = motion.frames[tick - first];
      const point = frame?.[1][robotIndex];
      const [x, y] = path[path.length - 1];
      if (
        frame?.[0] !== tick ||
        !point ||
        Math.abs(x - point[0]) + Math.abs(y - point[1]) > 1
      ) {
        return [next.position];
      }
      path.push(point);
    }
    const [x, y] = path[path.length - 1];
    if (x === next.position[0] && y === next.position[1]) return path;
    return [next.position];
  }
  return canInterpolate(previous, next)
    ? [previous.position, next.position]
    : [next.position];
}

export function positionOnPath(path: Point[], progress: number): Point {
  const segment = (path.length - 1) * Math.min(1, Math.max(0, progress));
  const from = path[Math.floor(segment)];
  const to = path[Math.ceil(segment)];
  const fraction = segment % 1;
  return [
    from[0] + (to[0] - from[0]) * fraction,
    from[1] + (to[1] - from[1]) * fraction,
  ];
}

export const motionDuration = (path: Point[], speed: number) =>
  path.length > 1
    ? Math.min(250, Math.max(48, (350 * (path.length - 1)) / speed))
    : 0;

export const robotColors = [
  "#2563eb",
  "#16a34a",
  "#d97706",
  "#7c3aed",
  "#0d9488",
  "#db2777",
  "#6f8330",
  "#475569",
];
export function worldPosition(
  [x, y]: Point,
  cellSize: number,
): [number, number, number] {
  return [(x + 0.5) * cellSize, 0, (y + 0.5) * cellSize];
}
