import { translateMessage } from "@/lib/i18n";
import { ChevronRight } from "lucide-react";
import {
  Collapsible,
  CollapsibleTrigger,
  CollapsibleContent,
} from "@/components/ui/collapsible";
import { format } from "@/lib/api";
import type { Simulation } from "@/types/domain";
const neuralActions = {
  task: "Převzít úkol",
  charge: "Nabít se",
  park: "Uvolnit stanici",
  idle: "Zůstat bez úkolu",
  move: "Popojet",
  wait: "Počkat",
} as const;
export function RunDetails({ simulation: s }: { simulation: Simulation }) {
  return (
    <Collapsible className="panel run-details">
      <CollapsibleTrigger className="details-trigger">
        <ChevronRight size={16} />
        <strong>Podrobnosti běhu</strong>
        <span>Metriky a události</span>
      </CollapsibleTrigger>
      <CollapsibleContent>
        {" "}
        <section className="event-panel">
          <div className="event-list">
            <div className="panel-heading">
              <h2>Záznam událostí</h2>
              <span className="subtle">
                Poslední události: {Math.min(5, s.events.length)}
              </span>
            </div>
            <div className="events">
              {s.events
                .slice(-5)
                .reverse()
                .map((e, i) => (
                  <div key={`${e.tick}-${i}`}>
                    <span className="event-tick">
                      {String(e.tick).padStart(4, "0")}
                    </span>
                    <i
                      className={e.type === "SIMULATION_ERROR" ? "bad" : "good"}
                    />
                    <span>{translateMessage(e.message)}</span>
                  </div>
                ))}
            </div>
          </div>
          <div className="run-summary">
            <h4>Metriky běhu</h4>
            <div className="detail-row">
              <span>
                {s.config.control === "neural"
                  ? "Čas rozhodování sítě"
                  : "Doba plánování"}
              </span>
              <strong>{format(s.metrics.planning_time_ms, 1)} ms</strong>
            </div>
            {s.config.control === "neural" ? (
              <>
                <div className="detail-row">
                  <span>Odmítnuté návrhy pohybu</span>
                  <strong>{s.neural_rejections}</strong>
                </div>
                <div className="detail-row">
                  <span>Automatické aktualizace vah</span>
                  <strong>{format(s.neural_updates)}</strong>
                </div>
              </>
            ) : (
              <>
                <div className="detail-row">
                  <span>Globální přeplánování</span>
                  <strong>{s.metrics.replans}</strong>
                </div>
                <div className="detail-row">
                  <span>Konflikty při plánování</span>
                  <strong>{s.metrics.planning_conflicts}</strong>
                </div>
              </>
            )}
            <div className="detail-row">
              <span>Propustnost</span>
              <strong>{format(s.metrics.throughput * 60, 2)} úkolů/min</strong>
            </div>
            {s.config.control === "neural" ? (
              <span className="subtle">
                Při konfliktu se vyhodnotí další návrh sítě.
              </span>
            ) : (
              <span className="subtle">
                Konflikty při plánování se počítají odděleně od vykonaných
                kolizí.
              </span>
            )}
          </div>
        </section>
        {s.config.control === "neural" && (
          <section className="learning-section" data-testid="neural-decisions">
            <div>
              <h2>Rozhodnutí neuronové sítě</h2>
              <p className="subtle">
                Model {s.neural_last_model_id ?? s.config.neural_model_id} ·
                poslední krok {s.tick}
              </p>
            </div>
            {s.neural_decisions.length ? (
              <div className="table-scroll">
                <table>
                  <thead>
                    <tr>
                      <th>Robot</th>
                      <th>Akce</th>
                      <th>Cílová buňka</th>
                      <th>Skóre</th>
                    </tr>
                  </thead>
                  <tbody>
                    {s.neural_decisions.map((d) => (
                      <tr key={`${d.robot_id}-${d.action}`}>
                        <td>{d.robot_id}</td>
                        <td>
                          {neuralActions[d.action]} {d.task_id}
                        </td>
                        <td>{d.target.join(", ")}</td>
                        <td>{format(d.score, 2)}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            ) : (
              <p className="subtle">
                V tomto kroku nebyla potřeba žádná akce sítě.
              </p>
            )}
          </section>
        )}
        {s.assignment_decisions?.length > 0 && (
          <section className="learning-section" data-testid="ml-decision">
            <div>
              <h2>Výběr robota podle ML</h2>
              <p className="subtle">
                Poslední přidělení: {s.assignment_decisions.at(-1)!.task_id} ·
                krok {s.assignment_decisions.at(-1)!.tick} · model{" "}
                {s.assignment_decisions.at(-1)!.model_id.slice(0, 8)}.
                Porovnávají se pouze dostupní roboti s dostatečnou baterií a
                nosností.
              </p>
            </div>
            <div className="table-scroll">
              <table>
                <thead>
                  <tr>
                    <th>Robot</th>
                    <th>Odhad bez učení</th>
                    <th>Odhad ML</th>
                    <th>Obsazení úseků</th>
                    <th>Protisměrné úseky</th>
                    <th>Rozhodnutí</th>
                  </tr>
                </thead>
                <tbody>
                  {[...s.assignment_decisions.at(-1)!.candidates]
                    .sort((a, b) => a.predicted_ticks - b.predicted_ticks)
                    .map((c) => (
                      <tr key={c.robot_id}>
                        <td>{c.robot_id}</td>
                        <td>{format(c.geometric_ticks, 1)} kroků</td>
                        <td>{format(c.predicted_ticks, 1)} kroků</td>
                        <td>{c.route_occupied}</td>
                        <td>{c.route_opposing_edges}</td>
                        <td>
                          {c.robot_id ===
                          s.assignment_decisions.at(-1)!.robot_id
                            ? "Vybrán"
                            : "—"}
                        </td>
                      </tr>
                    ))}
                </tbody>
              </table>
            </div>
            <p className="subtle">
              Odhad zahrnuje cestu k nákladu, přepravu a obsluhu. Model vybírá
              nejnižší odhad pro daný úkol; negarantuje nejrychlejší dokončení
              celého skladu.
            </p>
          </section>
        )}
      </CollapsibleContent>
    </Collapsible>
  );
}
