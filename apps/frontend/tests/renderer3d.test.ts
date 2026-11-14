import { describe, expect, it } from "vitest";
import { Vector3 } from "three";
import { canInterpolate, worldYaw } from "../src/renderers/shared/scene";
import { modelManifestSchema } from "../src/renderers/3d/modelSources";

describe("shared simulation → 3D contract", () => {
  it("faces the same four directions as the grid", () => {
    for (const [angle, expected] of [
      [0, [1, 0, 0]],
      [90, [0, 0, 1]],
      [180, [-1, 0, 0]],
      [-90, [0, 0, -1]],
    ] as const) {
      const direction = new Vector3(1, 0, 0).applyAxisAngle(
        new Vector3(0, 1, 0),
        worldYaw(angle),
      );
      direction.toArray().forEach((n, i) => expect(n).toBeCloseTo(expected[i]));
    }
  });
  it("snaps on reset, reconnect gaps, run changes and teleports", () => {
    const from = {
      run: "same",
      tick: 10,
      position: [2, 3] as [number, number],
    };
    expect(canInterpolate(from, { ...from, tick: 11, position: [3, 3] })).toBe(
      true,
    );
    expect(canInterpolate(from, { ...from, tick: 0 })).toBe(false);
    expect(canInterpolate(from, { ...from, tick: 12 })).toBe(false);
    expect(canInterpolate(from, { ...from, run: "other", tick: 11 })).toBe(
      false,
    );
    expect(canInterpolate(from, { ...from, tick: 11, position: [4, 4] })).toBe(
      false,
    );
  });
  it("accepts optional local GLBs and rejects unsupported or external paths", () => {
    expect(
      modelManifestSchema.parse({
        version: 1,
        models: { robot: "/models/robots/amr.glb", shelf: null },
      }).models.robot,
    ).toBe("/models/robots/amr.glb");
    for (const robot of [
      "https://external.example/robot.glb",
      "/models/../secret.glb",
      "/models/robot.blend",
    ])
      expect(
        modelManifestSchema.safeParse({ version: 1, models: { robot } })
          .success,
      ).toBe(false);
  });
});
