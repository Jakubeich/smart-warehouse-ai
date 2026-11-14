import { createContext, useContext } from "react";
import { z } from "zod";
import type { ModelKind } from "./assets";

const localGlb = z
  .string()
  .regex(/^\/models\/[a-zA-Z0-9_/-]+\.glb$/)
  .nullable();
export const modelManifestSchema = z.object({
  version: z.literal(1),
  models: z.object({
    robot: localGlb.optional(),
    shelf: localGlb.optional(),
    pickup: localGlb.optional(),
    dropoff: localGlb.optional(),
    charger: localGlb.optional(),
    pallet: localGlb.optional(),
    wall: localGlb.optional(),
    obstacle: localGlb.optional(),
  }),
});
export type ModelSources = Partial<Record<ModelKind, string | null>>;
export const ModelSourcesContext = createContext<ModelSources>({});
export const ModelReadyContext = createContext<(kind: ModelKind) => void>(
  () => {},
);
export const useModelSources = () => useContext(ModelSourcesContext);
