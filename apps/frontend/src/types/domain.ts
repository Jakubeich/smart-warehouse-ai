import { z } from "zod";
export const pointSchema = z.tuple([z.number().int(), z.number().int()]);
export const cellSchema = z.object({
  x: z.number().int(),
  y: z.number().int(),
  type: z.enum([
    "FLOOR",
    "WALL",
    "SHELF",
    "PICKUP",
    "DROPOFF",
    "CHARGER",
    "OBSTACLE",
  ]),
});
export const warehouseSchema = z.object({
  schema_version: z.literal(1),
  id: z.string(),
  name: z.string(),
  width: z.number(),
  height: z.number(),
  cell_size: z.number(),
  cells: z.array(cellSchema),
  metadata: z.record(z.string(), z.string()),
});
export const configSchema = z.object({
  control: z.enum(["classical", "neural"]).default("classical"),
  neural_model_id: z.string().nullable().default(null),
  planner: z.enum(["astar", "prioritized", "cbs", "adaptive"]),
  scheduler: z.enum(["nearest", "priority", "hungarian", "learned"]),
  ml_model_id: z.string().nullable().default(null),
  horizon: z.number(),
  max_nodes: z.number(),
  timeout_seconds: z.number(),
  move_energy: z.number(),
  wait_energy: z.number(),
  handling_energy: z.number(),
  charging_rate: z.number(),
  critical_threshold: z.number(),
  tick_seconds: z.number(),
});
export const robotSchema = z.object({
  id: z.string(),
  name: z.string(),
  position: pointSchema,
  home: pointSchema.nullable(),
  orientation: z.number(),
  status: z.string(),
  task_id: z.string().nullable(),
  path: z.array(pointSchema),
  path_index: z.number(),
  battery_capacity: z.number(),
  battery: z.number(),
  capacity: z.number(),
  load: z.number(),
  completed_tasks: z.number(),
  distance: z.number(),
  waiting: z.number(),
  busy_ticks: z.number(),
  mode: z.string(),
  service_remaining: z.number(),
  goal: pointSchema.nullable(),
});
export const taskSchema = z.object({
  id: z.string(),
  pickup: pointSchema,
  dropoff: pointSchema,
  priority: z.number(),
  created_tick: z.number(),
  assigned_robot: z.string().nullable(),
  status: z.string(),
  load_duration: z.number(),
  unload_duration: z.number(),
  assigned_tick: z.number().nullable(),
  pickup_tick: z.number().nullable(),
  completed_tick: z.number().nullable(),
  deadline: z.number().nullable(),
  payload_weight: z.number(),
});
export const scenarioSchema = z.object({
  schema_version: z.literal(1),
  id: z.string(),
  name: z.string(),
  warehouse: warehouseSchema,
  robots: z.array(robotSchema),
  tasks: z.array(taskSchema),
  seed: z.number(),
  config: configSchema,
});
export const metricsSchema = z.object({
  makespan: z.number(),
  sum_of_costs: z.number(),
  completed_tasks: z.number(),
  task_completion_rate: z.number(),
  average_task_completion_time: z.number(),
  total_distance: z.number(),
  total_waiting: z.number(),
  planning_time_ms: z.number(),
  replans: z.number(),
  planning_conflicts: z.number(),
  executed_collisions: z.number(),
  success: z.boolean(),
  throughput: z.number(),
});
export const stateSchema = z.object({
  schema_version: z.literal(1),
  id: z.string(),
  scenario_id: z.string(),
  name: z.string(),
  tick: z.number(),
  status: z.enum([
    "READY",
    "RUNNING",
    "PAUSED",
    "COMPLETED",
    "FAILED",
    "STOPPED",
  ]),
  config: configSchema,
  robots: z.array(robotSchema),
  tasks: z.array(taskSchema),
  warehouse: warehouseSchema,
  obstacles: z.array(pointSchema),
  events: z.array(
    z.object({
      tick: z.number(),
      type: z.string(),
      message: z.string(),
      entity_id: z.string().nullable(),
    }),
  ),
  metrics: metricsSchema,
  seed: z.number(),
  sequence: z.number(),
  speed: z.number(),
  reservations: z.array(
    z.object({
      robot_id: z.string(),
      x: z.number(),
      y: z.number(),
      tick: z.number(),
    }),
  ),
  conflicts: z.array(
    z.object({
      a: z.string(),
      b: z.string(),
      time: z.number(),
      vertex: pointSchema.nullable(),
      a_edge: z.tuple([pointSchema, pointSchema]).nullable(),
      b_edge: z.tuple([pointSchema, pointSchema]).nullable(),
    }),
  ),
  heatmap: z.record(z.string(), z.number()),
  history: z.array(
    z.object({
      tick: z.number(),
      completed: z.number(),
      waiting: z.number(),
      distance: z.number(),
      planning_ms: z.number(),
    }),
  ),
  error: z.string().nullable(),
  planner_status: z.string().nullable(),
  neural_decisions: z
    .array(
      z.object({
        robot_id: z.string(),
        action: z.enum(["task", "charge", "park", "idle", "move", "wait"]),
        target: pointSchema,
        task_id: z.string().nullable(),
        score: z.number(),
      }),
    )
    .default([]),
  neural_rejections: z.number().int().default(0),
  neural_last_model_id: z.string().nullable().default(null),
  neural_updates: z.number().int().default(0),
  neural_learned_samples: z.number().int().default(0),
  view_motion: z
    .object({
      episode: z.string(),
      frames: z
        .array(z.tuple([z.number().int(), z.array(pointSchema)]))
        .max(32),
    })
    .optional(),
  training_loop: z
    .object({
      active: z.boolean(),
      attempt: z.number().int(),
      finished_attempts: z.number().int(),
      best_completed_tasks: z.number().int(),
      last_result: z
        .object({
          status: z.enum(["COMPLETED", "FAILED"]),
          ticks: z.number().int(),
          completed_tasks: z.number().int(),
          model_updates: z.number().int(),
          error: z.string().nullable(),
        })
        .nullable(),
    })
    .nullable()
    .default(null),
  assignment_decisions: z
    .array(
      z.object({
        task_id: z.string(),
        robot_id: z.string(),
        tick: z.number(),
        model_id: z.string(),
        candidates: z.array(
          z.object({
            robot_id: z.string(),
            predicted_ticks: z.number(),
            geometric_ticks: z.number(),
            route_occupied: z.number().default(0),
            route_opposing_edges: z.number().default(0),
          }),
        ),
      }),
    )
    .default([]),
});
export const messageSchema = z.object({
  version: z.literal(1),
  type: z.literal("STATE_SNAPSHOT"),
  sequence: z.number().int(),
  state: stateSchema,
});
export type Point = z.infer<typeof pointSchema>;
export type Cell = z.infer<typeof cellSchema>;
export type Warehouse = z.infer<typeof warehouseSchema>;
export type Robot = z.infer<typeof robotSchema>;
export type Task = z.infer<typeof taskSchema>;
export type Config = z.infer<typeof configSchema>;
export type Scenario = z.infer<typeof scenarioSchema>;
export type Simulation = z.infer<typeof stateSchema>;
export type Metrics = z.infer<typeof metricsSchema>;
export const defaultConfig: Config = {
  control: "neural",
  neural_model_id: null,
  planner: "adaptive",
  scheduler: "priority",
  ml_model_id: null,
  horizon: 128,
  max_nodes: 2000,
  timeout_seconds: 2,
  move_energy: 0.4,
  wait_energy: 0,
  handling_energy: 0.1,
  charging_rate: 4,
  critical_threshold: 15,
  tick_seconds: 1,
};
export const plannerLabels: Record<Config["planner"], string> = {
  astar: "A* bez koordinace",
  prioritized: "Prioritizované plánování",
  cbs: "Řešení konfliktů (CBS)",
  adaptive: "Adaptivní prioritizované",
};
export const schedulerLabels: Record<Config["scheduler"], string> = {
  nearest: "Nejbližší dostupný robot",
  priority: "Podle priority úkolů",
  hungarian: "Maďarský algoritmus",
  learned: "ML odhad doby přepravy",
};
export const newRobot = (id: string, position: Point): Robot => ({
  id,
  name: `Atlas ${id}`,
  position,
  home: position,
  orientation: 0,
  status: "IDLE",
  task_id: null,
  path: [],
  path_index: 0,
  battery_capacity: 100,
  battery: 100,
  capacity: 50,
  load: 0,
  completed_tasks: 0,
  distance: 0,
  waiting: 0,
  busy_ticks: 0,
  mode: "IDLE",
  service_remaining: 0,
  goal: null,
});
export const newTask = (
  id: string,
  pickup: Point,
  dropoff: Point,
  priority = 1,
): Task => ({
  id,
  pickup,
  dropoff,
  priority,
  created_tick: 0,
  assigned_robot: null,
  status: "PENDING",
  load_duration: 2,
  unload_duration: 2,
  assigned_tick: null,
  pickup_tick: null,
  completed_tick: null,
  deadline: null,
  payload_weight: 10,
});
export interface ExperimentResult {
  algorithm: Config["planner"];
  scheduler: Config["scheduler"];
  seed: number;
  robots: number;
  status: string;
  success: boolean;
  optimal: boolean;
  reason: string | null;
  metrics: Metrics;
  wall_time_ms: number;
  source: "measured";
}
export interface ExperimentSummary {
  algorithm: Config["planner"];
  scheduler: Config["scheduler"];
  robots: number;
  runs: number;
  successful_runs: number;
  success_rate: number;
  metrics: Record<
    string,
    { mean: number | null; std: number | null; n: number }
  >;
}
export interface Experiment {
  id: string;
  name: string;
  status: string;
  created_at: string;
  config: { mode: string; benchmark: string };
  results: ExperimentResult[];
  summary: ExperimentSummary[];
  total_runs: number;
  environment: Record<string, string>;
  error?: string;
}
export interface DashboardData {
  warehouses: number;
  robots: number;
  active_simulations: number;
  completed_tasks: number;
  scenarios: Scenario[];
  experiments: Experiment[];
  runs: Simulation[];
}
