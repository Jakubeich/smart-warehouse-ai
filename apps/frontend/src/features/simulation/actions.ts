import { post } from "@/lib/api";
import { stateSchema, type Config } from "@/types/domain";
import { activeRunKey, usePreferences, useSimulation } from "@/stores/simulation";
export async function createRun(
  scenarioId: string,
  config: Config = usePreferences.getState().config,
) {
  const state = stateSchema.parse(
    await post("/simulations", {
      scenario_id: scenarioId,
      config,
      replace_id: sessionStorage.getItem(activeRunKey),
    }),
  );
  useSimulation.getState().setSimulation(state);
  useSimulation.getState().selectRobot(state.robots[0]?.id ?? null);
  return state;
}
export async function control(action: string, body: unknown = {}) {
  const id = useSimulation.getState().simulation?.id;
  if (!id) throw new Error("Nejprve vyberte scénář");
  const state = stateSchema.parse(
    await post(`/simulations/${id}/${action}`, body),
  );
  if (useSimulation.getState().simulation?.id === id)
    useSimulation.getState().setSimulation(state);
  return state;
}
