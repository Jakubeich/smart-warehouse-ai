import type { Metrics, Scenario } from "./domain";
export interface GeneratorOptions {
  name: string;
  width: number;
  height: number;
  density: number;
  layout: "aisles" | "islands" | "mixed";
  robot_count: number;
  task_count: number;
  seed: number;
  bottlenecks: boolean;
  passage_width: number;
  passage_count: number;
  traffic: "one_way" | "bidirectional";
}
export const defaultGenerator: GeneratorOptions = {
  name: "Generovaný sklad",
  width: 20,
  height: 16,
  density: 0.25,
  layout: "mixed",
  robot_count: 4,
  task_count: 20,
  seed: 42,
  bottlenecks: false,
  passage_width: 1,
  passage_count: 2,
  traffic: "one_way",
};
export interface LearnedModel {
  feature_version: number;
  id: string;
  created_at: string;
  algorithm: string;
  samples: number;
  train_samples: number;
  test_samples: number;
  train_layouts: string[];
  test_layouts: string[];
  feature_importance: Record<string, number>;
  metrics: {
    mae: number;
    rmse: number;
    baseline_mae: number;
    baseline_rmse: number;
  };
  validation_predictions: {
    actual: number;
    predicted: number;
    baseline: number;
  }[];
}
export interface LearningRun {
  scheduler: string;
  seed: number;
  status: string;
  reason: string | null;
  metrics: Metrics;
  source: "measured";
  mean_transport_ticks: number | null;
  assignments: Record<string, string | null>;
}
export interface ComparisonPair {
  seed: number;
  layout_key: string;
  unseen_layout: boolean;
  scenario: Scenario;
  baseline: LearningRun;
  learned: LearningRun;
}
export interface ComparisonSummary {
  pairs: number;
  successful_pairs: number;
  baseline_successes: number;
  learned_successes: number;
  different_assignments: number;
  metrics: Record<
    string,
    {
      baseline: number | null;
      learned: number | null;
      delta: number | null;
      improvement_percent: number | null;
    }
  >;
}
export interface LearningJob {
  id: string;
  action: "collect_train" | "train" | "compare";
  status: string;
  created_at: string;
  progress: number;
  total: number;
  message: string;
  error?: string;
  model_id: string | null;
  config: {
    baseline: "priority" | "nearest" | "hungarian";
    seed: number;
    max_ticks: number | null;
    generator?: GeneratorOptions;
    scenario_id?: string | null;
  };
  runs: LearningRun[];
  pairs: ComparisonPair[];
  summary: ComparisonSummary | null;
}
export interface LearningOverview {
  feature_version: number;
  archived_samples: number;
  dataset: {
    episodes: number;
    samples: number;
    layouts: number;
    unfinished: number;
    failed_runs: number;
    min_samples: number;
    min_layouts: number;
  };
  active_model_id: string | null;
  models: LearnedModel[];
  jobs: LearningJob[];
}
