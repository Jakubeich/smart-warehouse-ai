import { useQuery } from "@tanstack/react-query";
import { Play } from "lucide-react";
import { useNavigate } from "react-router-dom";
import { Button, ErrorPanel, Loading, useAction } from "@/components/shared";
import { api, format, post } from "@/lib/api";
import type { Scenario } from "@/types/domain";
import { createRun } from "./actions";

type Methods<T> = { classical: T; neural: T };
interface NeuralModel {
  id: string;
  initial_model_id: string;
  updates: number;
  learned_samples: number;
  update_ticks: number;
  architecture: number[];
  training: { maps: number; rows: number; epochs: number };
  evaluation: {
    pairs: number;
    both_completed: number;
    completed: Methods<number>;
    mean_ticks: Methods<number | null>;
    executed_collisions: number;
  } | null;
}

export function NeuralModelPanel() {
  const navigate = useNavigate();
  const { act, busy, error } = useAction();
  const query = useQuery({
    queryKey: ["neural-policy"],
    queryFn: () => api<NeuralModel>("/neural"),
    refetchInterval: 3000,
  });
  const model = query.data;
  const results = model?.evaluation;

  return (
    <section
      className="panel learning-section"
      aria-labelledby="neural-model-title"
    >
      <div className="panel-heading flex-wrap gap-3">
        <div>
          <h2 id="neural-model-title">Neuronové řízení flotily</h2>
          <p className="subtle">
            Síť vybírá úkoly, nabíječky a jednotlivé kroky robotů.
          </p>
        </div>
        {model && (
          <Button
            disabled={busy}
            onClick={() =>
              void act(async () => {
                const scenes = await post<Scenario[]>("/demos");
                const demo = scenes.find((scene) => scene.id === "demo-small");
                if (!demo) throw new Error("Ukázkový sklad není dostupný.");
                await createRun(demo.id);
                navigate("/simulation");
              })
            }
          >
            <Play data-icon="inline-start" /> Otevřít ukázkový sklad
          </Button>
        )}
      </div>
      <ErrorPanel error={error || query.error} />
      {query.isPending && <Loading />}
      {model && (
        <>
          <dl className="learning-facts">
            <div>
              <dt>Aktuální model</dt>
              <dd>{model.id}</dd>
            </div>
            <div>
              <dt>Automatické aktualizace vah</dt>
              <dd data-testid="neural-updates">{format(model.updates)}</dd>
            </div>
            <div>
              <dt>Použité zkušenosti z vlastních jízd</dt>
              <dd>{format(model.learned_samples)}</dd>
            </div>
          </dl>
          <p className="subtle">
            Váhy se ukládají po každých {model.update_ticks} krocích s novými
            zkušenostmi a při ukončení běhu.
          </p>
        </>
      )}
      {results && (
        <>
          <h3>Výchozí měření před průběžným učením</h3>
          <div className="table-scroll">
            <table>
              <thead>
                <tr>
                  <th>Na nových mapách</th>
                  <th className="whitespace-normal">Klasické řízení</th>
                  <th className="whitespace-normal">Neuronová síť</th>
                </tr>
              </thead>
              <tbody>
                <tr>
                  <td>Dokončené scénáře</td>
                  <td>
                    {results.completed.classical}/{results.pairs}
                  </td>
                  <td>
                    {results.completed.neural}/{results.pairs}
                  </td>
                </tr>
                <tr>
                  <td>Průměrná doba dokončení (kroky)</td>
                  <td>
                    {results.mean_ticks.classical === null
                      ? "—"
                      : format(results.mean_ticks.classical, 1)}
                  </td>
                  <td>
                    {results.mean_ticks.neural === null
                      ? "—"
                      : format(results.mean_ticks.neural, 1)}
                  </td>
                </tr>
              </tbody>
            </table>
          </div>
          <p className="subtle">
            Průměr z {results.both_completed} dvojic, kde dokončily obě metody.
            Vykonané kolize ve všech bězích: {results.executed_collisions}.
          </p>
        </>
      )}
    </section>
  );
}
