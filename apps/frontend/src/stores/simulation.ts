import { create } from "zustand";
import { persist } from "zustand/middleware";
import type { Config, Simulation } from "@/types/domain";
import { configSchema, defaultConfig } from "@/types/domain";
export const activeRunKey = "warehouse-active-run";
interface State {
  simulation: Simulation | null;
  selectedRobot: string | null;
  selectedTask: string | null;
  connection: "connecting" | "connected" | "disconnected";
  error: string | null;
  setSimulation: (state: Simulation) => void;
  selectRobot: (id: string | null) => void;
  selectTask: (id: string | null) => void;
  setConnection: (state: State["connection"]) => void;
  setError: (message: string | null) => void;
  clear: () => void;
}
export const useSimulation = create<State>((set) => ({
  simulation: null,
  selectedRobot: null,
  selectedTask: null,
  connection: "disconnected",
  error: null,
  setSimulation: (next) => {
    sessionStorage.setItem(activeRunKey, next.id);
    set((s) =>
      s.simulation?.id === next.id && s.simulation.sequence > next.sequence
        ? {}
        : { simulation: next, error: null },
    );
  },
  selectRobot: (id) => set({ selectedRobot: id, selectedTask: null }),
  selectTask: (id) => set({ selectedTask: id, selectedRobot: null }),
  setConnection: (connection) => set({ connection }),
  setError: (error) => set({ error }),
  clear: () => {
    sessionStorage.removeItem(activeRunKey);
    set({
      simulation: null,
      selectedRobot: null,
      selectedTask: null,
      connection: "disconnected",
      error: null,
    });
  },
}));
export interface Layers {
  grid: boolean;
  paths: boolean;
  ids: boolean;
  reservations: boolean;
  conflicts: boolean;
  stations: boolean;
  heatmap: boolean;
}
interface Preferences {
  config: Config;
  layers: Layers;
  viewMode: "2d" | "3d";
  setViewMode: (mode: "2d" | "3d") => void;
  setConfig: (config: Config) => void;
  toggleLayer: (layer: keyof Layers) => void;
}
export const usePreferences = create<Preferences>()(
  persist(
    (set) => ({
      config: defaultConfig,
      viewMode: "2d",
      setViewMode: (viewMode) => set({ viewMode }),
      layers: {
        grid: true,
        paths: true,
        ids: true,
        reservations: false,
        conflicts: true,
        stations: true,
        heatmap: false,
      },
      setConfig: (config) => set({ config }),
      toggleLayer: (layer) =>
        set((s) => ({ layers: { ...s.layers, [layer]: !s.layers[layer] } })),
    }),
    {
      name: "warehouse-preferences-v1",
      merge: (persisted, current) => {
        const stored = persisted as Partial<Preferences> | undefined;
        return {
          ...current,
          ...stored,
          config:
            configSchema.safeParse({
              ...stored?.config,
              control: "neural",
              neural_model_id: null,
              ml_model_id: null,
            }).data ?? current.config,
        };
      },
    },
  ),
);
