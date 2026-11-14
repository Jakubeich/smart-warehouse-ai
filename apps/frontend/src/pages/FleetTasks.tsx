import { counted, displayName, searchText } from "@/lib/i18n";
import { useState } from "react";
import { Link } from "react-router-dom";
import { Input } from "@/components/ui/input";
import { Button, PageHeader, EmptyState, Status } from "@/components/shared";
import { useSimulation } from "@/stores/simulation";
import { TaskDialog } from "@/features/tasks/TaskDialog";
import { format, human } from "@/lib/api";
export default function FleetTasks({ kind }: { kind: "robots" | "tasks" }) {
  const s = useSimulation((x) => x.simulation);
  const [filter, setFilter] = useState("");
  return (
    <>
      <PageHeader
        title={kind === "robots" ? "Flotila robotů" : "Přepravní úkoly"}
        description={
          kind === "robots"
            ? "Aktuální stav flotily, baterií a využití. Roboty upravíte v editoru skladu."
            : "Sledujte přepravu od přiřazení až po dokončení."
        }
      >
        {kind === "tasks" ? (
          <TaskDialog />
        ) : (
          <Button asChild variant="outline">
            <Link to="/warehouses">Upravit flotilu</Link>
          </Button>
        )}
      </PageHeader>
      {!s ? (
        <section className="panel">
          <EmptyState
            title="Žádná aktivní simulace"
            description="Otevřete scénář skladu a zobrazte jeho roboty a úkoly."
          >
            <Button asChild>
              <Link to="/simulation">Otevřít simulaci</Link>
            </Button>
          </EmptyState>
        </section>
      ) : (
        <section className="panel">
          <div className="panel-heading">
            <h2>{displayName(s.name)}</h2>
            <Input
              aria-label="Filtrovat záznamy"
              placeholder="Filtrovat podle ID, názvu nebo stavu…"
              value={filter}
              onChange={(e) => setFilter(e.target.value)}
            />
          </div>
          <div className="table-scroll">
            {kind === "robots" ? (
              <table>
                <thead>
                  <tr>
                    <th>Robot</th>
                    <th>Stav</th>
                    <th>Pozice</th>
                    <th>Baterie</th>
                    <th>Úkol</th>
                    <th>Vzdálenost</th>
                    <th>Čekání</th>
                    <th>Využití</th>
                  </tr>
                </thead>
                <tbody>
                  {s.robots
                    .filter((r) =>
                      searchText(
                        `${r.id} ${r.name} ${r.status} ${human(r.status)} ${human(r.mode)}`,
                      ).includes(searchText(filter)),
                    )
                    .map((r) => (
                      <tr key={r.id}>
                        <td>
                          <strong>{r.id}</strong>
                          <small>{r.name}</small>
                        </td>
                        <td>
                          <Status
                            value={r.mode === "OFFLINE" ? "OFFLINE" : r.status}
                          />
                        </td>
                        <td>({r.position.join(", ")})</td>
                        <td>
                          {format((r.battery / r.battery_capacity) * 100, 1)}%
                        </td>
                        <td>{r.task_id ?? "—"}</td>
                        <td>
                          {format(r.distance * s.warehouse.cell_size, 2)} m
                        </td>
                        <td>{counted(r.waiting, "tick")}</td>
                        <td>
                          {s.tick ? format((r.busy_ticks / s.tick) * 100) : 0}%
                        </td>
                      </tr>
                    ))}
                </tbody>
              </table>
            ) : (
              <table>
                <thead>
                  <tr>
                    <th>Úkol</th>
                    <th>Stav</th>
                    <th>Trasa</th>
                    <th>Priorita</th>
                    <th>Robot</th>
                    <th>Náklad</th>
                    <th>Vytvořeno</th>
                    <th>Dokončeno</th>
                  </tr>
                </thead>
                <tbody>
                  {s.tasks
                    .filter((t) =>
                      searchText(
                        `${t.id} ${t.status} ${human(t.status)}`,
                      ).includes(searchText(filter)),
                    )
                    .map((t) => (
                      <tr key={t.id}>
                        <td>{t.id}</td>
                        <td>
                          <Status value={t.status} />
                        </td>
                        <td>
                          ({t.pickup.join(",")}) → ({t.dropoff.join(",")})
                        </td>
                        <td>{t.priority}</td>
                        <td>{t.assigned_robot ?? "—"}</td>
                        <td>{format(t.payload_weight, 2)} kg</td>
                        <td>{t.created_tick}</td>
                        <td>{t.completed_tick ?? "—"}</td>
                      </tr>
                    ))}
                </tbody>
              </table>
            )}
          </div>
        </section>
      )}
    </>
  );
}
