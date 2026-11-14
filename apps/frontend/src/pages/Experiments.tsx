import { displayName, formatDate, translateMessage, counted } from "@/lib/i18n";
import { useQuery } from "@tanstack/react-query";
import { useSearchParams } from "react-router-dom";
import { Download, Square } from "lucide-react";
import {
  Bar,
  BarChart,
  CartesianGrid,
  Line,
  LineChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import { Tabs, TabsList, TabsTrigger, TabsContent } from "@/components/ui/tabs";
import {
  Button,
  PageHeader,
  ErrorPanel,
  EmptyState,
  Status,
  useAction,
} from "@/components/shared";
import { api, post, format } from "@/lib/api";
import {
  plannerLabels,
  schedulerLabels,
  type Experiment,
} from "@/types/domain";
export default function Experiments() {
  const [params, setParams] = useSearchParams();
  const id = params.get("id");
  const { act, error } = useAction();
  const jobs = useQuery({
    queryKey: ["experiments"],
    queryFn: () => api<Experiment[]>("/experiments"),
    refetchInterval: 3000,
  });
  const job = useQuery({
    queryKey: ["experiment", id],
    queryFn: () => api<Experiment>(`/experiments/${id}`),
    enabled: !!id,
    refetchInterval: (q) => (q.state.data?.status === "RUNNING" ? 600 : false),
  });
  const data = job.data;
  const chart =
    data?.summary.map((s) => ({
      name: `${plannerLabels[s.algorithm]} · ${s.robots}`,
      planning: s.metrics.planning_time_ms?.mean ?? 0,
      makespan: s.metrics.makespan?.mean ?? null,
      success: s.success_rate * 100,
    })) ?? [];
  return (
    <>
      <PageHeader
        title="Experimenty"
        description="Archiv srovnávacích měření plánovačů a přiřazování úkolů."
      ></PageHeader>
      <ErrorPanel error={error || job.error || jobs.error} />
      <div className="experiment-results">
        <Tabs defaultValue="summary">
          <TabsList>
            <TabsTrigger value="summary">Přehled</TabsTrigger>
            <TabsTrigger value="charts" disabled={!data}>
              Grafy
            </TabsTrigger>
            <TabsTrigger value="outcomes" disabled={!data}>
              Jednotlivé běhy
            </TabsTrigger>
          </TabsList>
          <TabsContent value="summary">
            <section className="panel">
              <div className="panel-heading">
                <h2>Naměřené výsledky</h2>
                <div className="inline-actions">
                  {data && (
                    <>
                      <Status value={data.status} />
                      <a
                        href={`/api/experiments/${data.id}/results?format=csv`}
                        download
                      >
                        <Button variant="outline" size="sm">
                          <Download data-icon="inline-start" />
                          CSV
                        </Button>
                      </a>
                      <a
                        href={`/api/experiments/${data.id}/results`}
                        download={`experiment-${data.id}.json`}
                      >
                        <Button variant="outline" size="sm">
                          JSON
                        </Button>
                      </a>
                      {data.status === "RUNNING" && (
                        <Button
                          variant="outline"
                          size="sm"
                          onClick={() =>
                            void act(async () => {
                              await post(`/experiments/${data.id}/cancel`);
                              await job.refetch();
                            })
                          }
                        >
                          <Square data-icon="inline-start" />
                          Zrušit
                        </Button>
                      )}
                    </>
                  )}
                </div>
              </div>
              {!data ? (
                <EmptyState
                  title="Nejsou vybrané žádné výsledky"
                  description="Vyberte uložené měření a prohlédněte si jeho výsledky včetně neúspěšných běhů."
                />
              ) : (
                <>
                  <div className="result-heading">
                    <h3>{displayName(data.name)}</h3>
                    <p>
                      Naměřené běhy: {data.results.length} / {data.total_runs}·{" "}
                      {data.config.mode === "mapf"
                        ? "statický MAPF"
                        : "přeprava"}{" "}
                      · scénář {data.config.benchmark}
                    </p>
                    {data.status === "CANCELLED" && (
                      <p>
                        Bylo vyžádáno zrušení. Aktuální běh může před ukončením
                        doběhnout do nastaveného limitu.
                      </p>
                    )}
                    <ErrorPanel error={data.error} />
                  </div>
                  <div className="table-scroll">
                    <table>
                      <thead>
                        <tr>
                          <th>Plánovač / přiřazování</th>
                          <th>Roboti</th>
                          <th>Úspěšnost</th>
                          <th>Doba dokončení ± σ</th>
                          <th>SoC ± σ</th>
                          <th>Plánování (ms) ± σ</th>
                        </tr>
                      </thead>
                      <tbody>
                        {data.summary.map((s, i) => (
                          <tr key={i}>
                            <td>
                              <strong>{plannerLabels[s.algorithm]}</strong>
                              <small>{schedulerLabels[s.scheduler]}</small>
                            </td>
                            <td>{s.robots}</td>
                            <td>
                              {s.successful_runs}/{s.runs}
                            </td>
                            {[
                              "makespan",
                              "sum_of_costs",
                              "planning_time_ms",
                            ].map((key) => (
                              <td key={key}>
                                {s.metrics[key]?.mean == null
                                  ? "—"
                                  : `${format(s.metrics[key].mean, 2)} ± ${format(s.metrics[key].std ?? 0, 2)}`}
                              </td>
                            ))}
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                  <p className="table-note">
                    Cena cest a doba dokončení zahrnují jen úspěšné běhy; doba
                    plánování zahrnuje i neúspěšné. σ je populační směrodatná
                    odchylka. Ve statickém MAPF znamenají dokončené úkoly
                    dosažené cíle.
                  </p>
                </>
              )}
            </section>
          </TabsContent>
          <TabsContent value="charts">
            {" "}
            {data && chart.length > 0 && (
              <div className="two-columns">
                <section className="panel chart-panel">
                  <h3>Doba plánování</h3>
                  <p>Průměrný skutečný čas v milisekundách</p>
                  <ResponsiveContainer width="100%" height={220}>
                    <BarChart data={chart}>
                      <CartesianGrid stroke="var(--border)" vertical={false} />
                      <XAxis dataKey="name" fontSize={10} />
                      <YAxis fontSize={11} />
                      <Tooltip
                        formatter={(value) => format(Number(value), 2)}
                        contentStyle={{
                          background: "var(--popover)",
                          borderColor: "var(--border)",
                        }}
                      />
                      <Bar
                        dataKey="planning"
                        name="Doba plánování (ms)"
                        fill="var(--primary)"
                        radius={[3, 3, 0, 0]}
                      />
                    </BarChart>
                  </ResponsiveContainer>
                </section>
                <section className="panel chart-panel">
                  <h3>Doba dokončení podle skupin</h3>
                  <p>Úspěšné běhy, simulované kroky</p>
                  <ResponsiveContainer width="100%" height={220}>
                    <LineChart data={chart}>
                      <CartesianGrid stroke="var(--border)" />
                      <XAxis dataKey="name" fontSize={10} />
                      <YAxis fontSize={11} />
                      <Tooltip
                        formatter={(value) => format(Number(value), 2)}
                        contentStyle={{
                          background: "var(--popover)",
                          borderColor: "var(--border)",
                        }}
                      />
                      <Line
                        dataKey="makespan"
                        name="Doba dokončení (kroky)"
                        stroke="var(--primary)"
                        strokeWidth={2}
                      />
                    </LineChart>
                  </ResponsiveContainer>
                </section>
              </div>
            )}
          </TabsContent>
          <TabsContent value="outcomes">
            {" "}
            {data && (
              <section className="panel">
                <div className="panel-heading">
                  <h2>Výsledky jednotlivých běhů</h2>
                  <span className="subtle">Zdroj: provedený experiment</span>
                </div>
                <div className="table-scroll">
                  <table>
                    <thead>
                      <tr>
                        <th>Algoritmus</th>
                        <th>Seed</th>
                        <th>Stav</th>
                        <th>Optimalita</th>
                        <th>Podrobnosti</th>
                      </tr>
                    </thead>
                    <tbody>
                      {data.results.map((r, i) => (
                        <tr key={i}>
                          <td>{plannerLabels[r.algorithm]}</td>
                          <td>{r.seed}</td>
                          <td>
                            <Status value={r.status} />
                          </td>
                          <td>
                            {r.optimal
                              ? "Optimální statický SoC"
                              : "Bez záruky"}
                          </td>
                          <td>
                            {(r.reason ? translateMessage(r.reason) : null) ||
                              `${format(r.metrics.total_distance)} m · ${r.metrics.executed_collisions} vykonaných kolizí`}
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
                <div className="environment">
                  <strong>Prostředí měření</strong>
                  <p>
                    {data.environment.platform} · {data.environment.machine}
                  </p>
                  <p>{data.environment.python}</p>
                </div>
              </section>
            )}
          </TabsContent>
        </Tabs>{" "}
        <section className="panel">
          <div className="panel-heading">
            <h2>Uložené experimenty</h2>
          </div>
          {jobs.data?.length ? (
            <div className="row-list">
              {jobs.data.map((saved) => {
                const j = data && saved.id === data.id ? data : saved;
                return (
                  <button key={j.id} onClick={() => setParams({ id: j.id })}>
                    <div>
                      <strong>{displayName(j.name)}</strong>
                      <small>
                        {formatDate(j.created_at)} ·{" "}
                        {counted(j.results.length, "run")}
                      </small>
                    </div>
                    <Status value={j.status} />
                  </button>
                );
              })}
            </div>
          ) : (
            <EmptyState
              title="Zatím žádné experimenty"
              description="Výsledky se automaticky ukládají do PostgreSQL."
            />
          )}
        </section>
      </div>
    </>
  );
}
