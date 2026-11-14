import { counted, displayName } from "@/lib/i18n";
import { useQuery } from "@tanstack/react-query";
import { useState } from "react";
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
import { CheckCircle2, Route, Clock3, Activity } from "lucide-react";
import { PageHeader, Picker, EmptyState, ErrorPanel, Metric } from "@/components/shared";
import { useSimulation } from "@/stores/simulation";
import { api, format } from "@/lib/api";
import type { Simulation } from "@/types/domain";
export default function Analytics() {
  const live = useSimulation((s) => s.simulation);
  const [id, setId] = useState("live");
  const runs = useQuery({
    queryKey: ["runs"],
    queryFn: () => api<Simulation[]>("/runs"),
  });
  const s = id === "live" ? live : runs.data?.find((r) => r.id === id);
  const tooltip = {
    background: "var(--popover)",
    borderColor: "var(--border)",
  };
  return (
    <>
      <PageHeader
        title="Analýza výkonu"
        description="Vyhodnoťte propustnost, čekání a energii z naměřeného průběhu."
      >
        <Picker
          label="Analyzovaný běh"
          value={id}
          onChange={setId}
          options={[
            { value: "live", label: "Aktuální simulace" },
            ...(runs.data ?? []).map((r) => ({
              value: r.id,
              label: `${displayName(r.name)} · ${counted(r.tick, "tick")}`,
            })),
          ]}
        />
      </PageHeader>
      <ErrorPanel error={runs.error} />
      {!s ? (
        <section className="panel">
          <EmptyState
            title="Žádná data simulace"
            description="Spusťte simulaci nebo vyberte uložený běh pro zobrazení výsledků."
          />
        </section>
      ) : (
        <>
          <div className="metrics-grid">
            <Metric
              label="Dokončené úkoly"
              value={format(s.metrics.task_completion_rate * 100)}
              unit="%"
              icon={CheckCircle2}
              tone="green"
            />
            <Metric
              label="Průměrná doba dokončení"
              value={format(s.metrics.average_task_completion_time, 1)}
              unit="kroků"
              icon={Clock3}
            />
            <Metric
              label="Propustnost"
              value={format(s.metrics.throughput * 60, 2)}
              unit="úkolů/min"
              icon={Activity}
            />
            <Metric
              label="Celková vzdálenost"
              value={s.metrics.total_distance}
              unit="m"
              icon={Route}
            />
          </div>
          <div className="two-columns">
            <section className="panel chart-panel">
              <h3>Dokončené úkoly v čase</h3>
              <p>Historie kroků ze simulačního enginu</p>
              <ResponsiveContainer width="100%" height={280}>
                <LineChart data={s.history}>
                  <CartesianGrid stroke="var(--border)" />
                  <XAxis dataKey="tick" />
                  <YAxis allowDecimals={false} />
                  <Tooltip
                    contentStyle={tooltip}
                    formatter={(value) => format(Number(value), 2)}
                  />
                  <Line
                    type="stepAfter"
                    dataKey="completed"
                    name="Dokončené úkoly"
                    stroke="#15803d"
                    dot={false}
                    strokeWidth={2}
                  />
                </LineChart>
              </ResponsiveContainer>
            </section>
            <section className="panel chart-panel">
              <h3>Čekání a plánování</h3>
              <p>Celkové čekání v krocích a plánování v milisekundách</p>
              <ResponsiveContainer width="100%" height={280}>
                <LineChart data={s.history}>
                  <CartesianGrid stroke="var(--border)" />
                  <XAxis dataKey="tick" />
                  <YAxis yAxisId="wait" />
                  <YAxis yAxisId="plan" orientation="right" />
                  <Tooltip
                    contentStyle={tooltip}
                    formatter={(value) => format(Number(value), 2)}
                  />
                  <Line
                    yAxisId="wait"
                    dataKey="waiting"
                    name="Čekání (kroky)"
                    stroke="#a16207"
                    dot={false}
                  />
                  <Line
                    yAxisId="plan"
                    dataKey="planning_ms"
                    name="Plánování (ms)"
                    stroke="var(--primary)"
                    dot={false}
                  />
                </LineChart>
              </ResponsiveContainer>
            </section>
            <section className="panel chart-panel">
              <h3>Baterie a využití flotily</h3>
              <p>Procenta kapacity / podíl pracovních kroků</p>
              <ResponsiveContainer width="100%" height={260}>
                <BarChart
                  data={s.robots.map((r) => ({
                    id: r.id,
                    battery: (r.battery / r.battery_capacity) * 100,
                    utilization: s.tick ? (r.busy_ticks / s.tick) * 100 : 0,
                  }))}
                >
                  <CartesianGrid stroke="var(--border)" />
                  <XAxis dataKey="id" />
                  <YAxis domain={[0, 100]} />
                  <Tooltip
                    contentStyle={tooltip}
                    formatter={(value) => format(Number(value), 2)}
                  />
                  <Bar name="Baterie (%)" dataKey="battery" fill="#15803d" />
                  <Bar
                    name="Využití (%)"
                    dataKey="utilization"
                    fill="var(--primary)"
                  />
                </BarChart>
              </ResponsiveContainer>
            </section>
            <section className="panel chart-panel">
              <h3>Teplotní mapa obsazenosti</h3>
              <p>Skutečná obsazenost buněk včetně čekání</p>
              <div
                className="heatmap"
                style={{
                  gridTemplateColumns: `repeat(${s.warehouse.width},1fr)`,
                }}
              >
                {Array.from(
                  { length: s.warehouse.width * s.warehouse.height },
                  (_, i) => {
                    const x = i % s.warehouse.width,
                      y = Math.floor(i / s.warehouse.width),
                      count = s.heatmap[`${x},${y}`] ?? 0,
                      max = Math.max(1, ...Object.values(s.heatmap));
                    const blocked = s.warehouse.cells.some(
                      (c) =>
                        c.x === x &&
                        c.y === y &&
                        ["SHELF", "WALL"].includes(c.type),
                    );
                    return (
                      <i
                        key={i}
                        title={`(${x},${y}): ${count} robotokroků`}
                        style={{
                          background: blocked
                            ? "#3a4e60"
                            : `rgba(55,195,205,${count ? 0.12 + (0.88 * count) / max : 0.025})`,
                        }}
                      />
                    );
                  },
                )}
              </div>
              <p className="table-note">
                Najeďte na buňku pro počet návštěv. Regály jsou šedé.
              </p>
            </section>
          </div>
        </>
      )}
    </>
  );
}
