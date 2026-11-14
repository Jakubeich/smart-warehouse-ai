import { describe, it, expect, vi } from "vitest";
import { post, api } from "../src/lib/api";
import { createRun } from "../src/features/simulation/actions";
import { stateSchema, messageSchema } from "../src/types/domain";
import { useSimulation } from "../src/stores/simulation";
import { worldPosition } from "../src/renderers/shared/scene";
vi.mock("../src/lib/api", () => ({ post: vi.fn(), api: vi.fn() }));
const state = stateSchema.parse({
  schema_version: 1,
  id: "test",
  scenario_id: "scenario",
  name: "Test",
  tick: 4,
  status: "PAUSED",
  config: {
    planner: "cbs",
    scheduler: "nearest",
    horizon: 128,
    max_nodes: 2000,
    timeout_seconds: 2,
    move_energy: 0.4,
    wait_energy: 0,
    handling_energy: 0.1,
    charging_rate: 4,
    critical_threshold: 15,
    tick_seconds: 1,
  },
  robots: [],
  tasks: [],
  warehouse: {
    schema_version: 1,
    id: "w",
    name: "W",
    width: 4,
    height: 4,
    cell_size: 1,
    cells: [],
    metadata: {},
  },
  obstacles: [],
  events: [],
  metrics: {
    makespan: 4,
    sum_of_costs: 0,
    completed_tasks: 0,
    task_completion_rate: 0,
    average_task_completion_time: 0,
    total_distance: 0,
    total_waiting: 0,
    planning_time_ms: 0,
    replans: 0,
    planning_conflicts: 0,
    executed_collisions: 0,
    success: false,
    throughput: 0,
  },
  seed: 42,
  sequence: 10,
  speed: 1,
  reservations: [],
  conflicts: [],
  heatmap: {},
  history: [],
  error: null,
  planner_status: null,
});
describe("authoritative snapshots", () => {
  it("rejects stale snapshots and accepts reset with newer sequence", () => {
    const store = useSimulation.getState();
    store.clear();
    store.setSimulation(state);
    store.setSimulation({ ...state, sequence: 9, tick: 99 });
    expect(useSimulation.getState().simulation?.tick).toBe(4);
    store.setSimulation({ ...state, sequence: 11, tick: 0 });
    expect(useSimulation.getState().simulation?.tick).toBe(0);
  });
  it("validates the protocol version and payload", () => {
    expect(
      messageSchema.safeParse({
        version: 2,
        type: "STATE_SNAPSHOT",
        sequence: 10,
        state,
      }).success,
    ).toBe(false);
    expect(
      messageSchema.safeParse({
        version: 1,
        type: "STATE_SNAPSHOT",
        sequence: 10,
        state,
      }).success,
    ).toBe(true);
  });
  it("maps cell centres into future 3D without altering domain coordinates", () => {
    expect(worldPosition([2, 3], 2)).toEqual([5, 0, 7]);
  });
  it("preserves the current simulation when the requested ML model is unavailable", async () => {
    vi.clearAllMocks();
    useSimulation.getState().clear();
    useSimulation.getState().setSimulation(state);
    vi.mocked(post).mockRejectedValueOnce(
      new Error("Nejdříve natrénujte model"),
    );
    await expect(
      createRun("scenario", { ...state.config, scheduler: "learned" }),
    ).rejects.toThrow("model");
    expect(api).not.toHaveBeenCalled();
    expect(useSimulation.getState().simulation).toEqual(state);
  });
});
