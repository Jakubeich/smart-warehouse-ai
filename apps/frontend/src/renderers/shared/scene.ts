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
