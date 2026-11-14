/** GLB models use metres, Y up, +X forward, origin at floor centre.
 * A one-cell template is scaled uniformly by warehouse.cell_size.
 * Connect real files through public/models/manifest.json. No empty GLBs.
 */
export const modelCatalog = {
  robot: {
    label: "Mobilní robot",
    file: "robots/amr.glb",
    size: "0,78 × 0,58 × 0,38 m",
  },
  shelf: {
    label: "Regál",
    file: "warehouse/shelf.glb",
    size: "0,92 × 0,92 × 1,65 m",
  },
  pickup: {
    label: "Nakládací stanice",
    file: "warehouse/pickup.glb",
    size: "0,92 × 0,92 × 0,8 m",
  },
  dropoff: {
    label: "Vykládací stanice",
    file: "warehouse/dropoff.glb",
    size: "0,92 × 0,92 × 0,8 m",
  },
  charger: {
    label: "Nabíjecí stanice",
    file: "warehouse/charger.glb",
    size: "0,92 × 0,92 × 0,55 m",
  },
  pallet: {
    label: "Paleta s nákladem",
    file: "warehouse/pallet.glb",
    size: "0,55 × 0,48 × 0,32 m",
  },
  wall: {
    label: "Stěna",
    file: "warehouse/wall.glb",
    size: "1 × 1 × 1,6 m",
  },
  obstacle: {
    label: "Dynamická překážka",
    file: "warehouse/obstacle.glb",
    size: "0,8 × 0,8 × 0,6 m",
  },
};
export type ModelKind = keyof typeof modelCatalog;
export const cellModels: Record<string, ModelKind> = {
  SHELF: "shelf",
  WALL: "wall",
  PICKUP: "pickup",
  DROPOFF: "dropoff",
  CHARGER: "charger",
  OBSTACLE: "obstacle",
};
export type BoxPart = {
  position: [number, number, number];
  size: [number, number, number];
  color: string;
};
export function placeholderParts(
  kind: ModelKind,
  color = "#4f46e5",
): BoxPart[] {
  const box = (
    position: BoxPart["position"],
    size: BoxPart["size"],
    color: string,
  ): BoxPart => ({ position, size, color });
  switch (kind) {
    case "robot":
      return [
        box([0, 0.17, 0], [0.78, 0.24, 0.58], "#e2e8f0"),
        box([0, 0.3, 0], [0.7, 0.08, 0.52], color),
        box([0.4, 0.18, 0], [0.035, 0.08, 0.26], "#334155"),
        ...[-0.23, 0.23].flatMap((x) =>
          [-0.29, 0.29].map((z) =>
            box([x, 0.1, z], [0.17, 0.18, 0.07], "#334155"),
          ),
        ),
      ];
    case "shelf":
      return [
        ...[-0.42, 0.42].flatMap((x) =>
          [-0.42, 0.42].map((z) =>
            box([x, 0.8, z], [0.055, 1.6, 0.055], "#64748b"),
          ),
        ),
        ...[0.12, 0.85, 1.58].map((y) =>
          box([0, y, 0], [0.92, 0.07, 0.92], "#d9a35d"),
        ),
        box([-0.2, 0.42, 0], [0.32, 0.51, 0.62], "#d4c6af"),
        box([0.2, 0.39, 0.05], [0.3, 0.45, 0.52], "#b9c7ce"),
        box([0, 1.1, 0], [0.65, 0.42, 0.66], "#c9b99e"),
      ];
    case "pickup":
    case "dropoff":
    case "charger": {
      const accent =
        kind === "pickup"
          ? "#60a5fa"
          : kind === "dropoff"
            ? "#4ade80"
            : "#fbbf24";
      return [
        box([0, 0.025, 0], [0.92, 0.05, 0.92], accent),
        box(
          [-0.4, kind === "charger" ? 0.22 : 0.38, 0],
          [0.12, kind === "charger" ? 0.44 : 0.76, 0.58],
          "#cbd5e1",
        ),
        box([-0.33, 0.3, 0], [0.025, 0.18, 0.25], "#334155"),
      ];
    }
    case "pallet":
      return [
        box([0, 0.045, 0], [0.55, 0.09, 0.48], "#a47e4f"),
        box([0, 0.2, 0], [0.49, 0.22, 0.43], "#d1b38b"),
      ];
    case "wall":
      return [box([0, 0.8, 0], [1, 1.6, 1], "#94a3b8")];
    case "obstacle":
      return [
        box([0, 0.3, 0], [0.8, 0.6, 0.8], "#fb923c"),
        box([0, 0.47, 0], [0.82, 0.09, 0.82], "#fff7ed"),
      ];
  }
}
