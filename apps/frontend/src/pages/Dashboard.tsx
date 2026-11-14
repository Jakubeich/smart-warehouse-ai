import { counted, displayName } from "@/lib/i18n";
import { useState } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { useNavigate } from "react-router-dom";
import { Box, FlaskConical, Play, Trash2 } from "lucide-react";
import { toast } from "sonner";
import {
  Button,
  PageHeader,
  Loading,
  ErrorPanel,
  EmptyState,
  Status,
  useAction,
} from "@/components/shared";
import {
  Dialog,
  DialogClose,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
  DialogTrigger,
} from "@/components/ui/dialog";
import { api, post, format } from "@/lib/api";
import type { DashboardData, Scenario } from "@/types/domain";
import { createRun } from "@/features/simulation/actions";
export default function Dashboard() {
  const q = useQuery({
    queryKey: ["dashboard"],
    queryFn: () => api<DashboardData>("/dashboard"),
    refetchInterval: 5000,
  });
  const client = useQueryClient();
  const navigate = useNavigate();
  const { act, busy, error } = useAction();
  if (q.isPending) return <Loading />;
  if (q.error) return <ErrorPanel error={q.error} />;
  const d = q.data;
  return (
    <>
      <PageHeader
        title="Přehled"
        description="Vyberte sklad a otevřete simulaci."
      >
        <Button
          variant="outline"
          disabled={busy}
          onClick={() =>
            void act(async () => {
              await post("/demos");
              await client.invalidateQueries();
            })
          }
        >
          <PlusIcon />
          Vytvořit ukázkové scénáře
        </Button>
      </PageHeader>
      <ErrorPanel error={error} />
      <section className="panel">
        <div className="panel-heading">
          <div>
            <h2>Scénáře skladů</h2>
          </div>
          <span className="subtle">
            {counted(d.scenarios.length, "scenario")}
          </span>
        </div>
        {!d.scenarios.length ? (
          <EmptyState
            title="Vytvořte první sklad"
            description="Vytvořte tři ukázkové scénáře nebo navrhněte vlastní sklad v editoru."
          >
            <Button variant="outline" onClick={() => navigate("/warehouses")}>
              Otevřít editor skladu
            </Button>
          </EmptyState>
        ) : (
          <div className="scenario-grid">
            {d.scenarios.map((s) => (
              <article key={s.id} className="scenario-card">
                <div className="scenario-name">
                  <Box size={20} />
                  <div>
                    <h3>{displayName(s.name)}</h3>
                    <p>
                      {s.warehouse.width} × {s.warehouse.height} buněk{" "}
                      <span>·</span> {counted(s.robots.length, "robot")}{" "}
                      <span>·</span> {counted(s.tasks.length, "task")}
                    </p>
                  </div>
                </div>
                <div className="inline-actions scenario-actions">
                  <Button
                    variant="outline"
                    disabled={busy}
                    onClick={() =>
                      void act(async () => {
                        await createRun(s.id);
                        navigate("/simulation");
                      })
                    }
                  >
                    <Play data-icon="inline-start" />
                    Otevřít simulaci
                  </Button>
                  <DeleteScenario scenario={s} disabled={busy} />
                </div>
              </article>
            ))}
          </div>
        )}
      </section>
      <div className="two-columns">
        <section className="panel">
          <div className="panel-heading">
            <h2>Poslední experimenty</h2>
            <FlaskConical size={18} />
          </div>
          {d.experiments.length ? (
            <div className="row-list">
              {d.experiments.map((e) => (
                <button
                  key={e.id}
                  onClick={() => navigate(`/experiments?id=${e.id}`)}
                >
                  <div>
                    <strong>{displayName(e.name)}</strong>
                    <small>Naměřené běhy: {e.results.length}</small>
                  </div>
                  <Status value={e.status} />
                </button>
              ))}
            </div>
          ) : (
            <EmptyState
              title="Zatím žádné experimenty"
              description="Uložená srovnávací měření najdete v archivu experimentů."
            >
              <Button
                variant="outline"
                onClick={() => navigate("/experiments")}
              >
                Otevřít archiv experimentů
              </Button>
            </EmptyState>
          )}
        </section>
        <section className="panel">
          <div className="panel-heading">
            <h2>Dokončené běhy</h2>
            <Box size={18} />
          </div>
          {d.runs.length ? (
            <div className="row-list">
              {d.runs.slice(0, 4).map((r) => (
                <div key={r.id}>
                  <div>
                    <strong>{displayName(r.name)}</strong>
                    <small>
                      {counted(r.metrics.completed_tasks, "task")} ·{" "}
                      {counted(r.tick, "tick")} ·{" "}
                      {format(r.metrics.total_distance)} m
                    </small>
                  </div>
                  <Status value={r.status} />
                </div>
              ))}
            </div>
          ) : (
            <EmptyState
              title="Zatím žádné dokončené běhy"
              description="Zde se zobrazí dokončené simulace a jejich naměřené výsledky."
            />
          )}
        </section>
      </div>
    </>
  );
}

function DeleteScenario({
  scenario,
  disabled,
}: {
  scenario: Scenario;
  disabled: boolean;
}) {
  const [open, setOpen] = useState(false);
  const client = useQueryClient();
  const { act, busy, error } = useAction();
  const name = displayName(scenario.name);

  return (
    <Dialog open={open} onOpenChange={(next) => !busy && setOpen(next)}>
      <DialogTrigger asChild>
        <Button
          variant="outline"
          size="icon"
          aria-label={`Smazat scénář ${name}`}
          title="Smazat scénář"
          disabled={disabled || busy}
        >
          <Trash2 />
        </Button>
      </DialogTrigger>
      <DialogContent showCloseButton={false}>
        <DialogHeader>
          <DialogTitle>Smazat scénář?</DialogTitle>
          <DialogDescription>
            Uložený scénář „{name}“ bude trvale odstraněn.
          </DialogDescription>
        </DialogHeader>
        <ErrorPanel error={error} />
        <DialogFooter>
          <DialogClose asChild>
            <Button variant="outline" disabled={busy}>
              Zrušit
            </Button>
          </DialogClose>
          <Button
            variant="destructive"
            disabled={busy}
            onClick={() =>
              void act(async () => {
                const query = new URLSearchParams({ scenario_id: scenario.id });
                await api(`/scenarios?${query}`, { method: "DELETE" });
                setOpen(false);
                await Promise.all([
                  client.invalidateQueries({ queryKey: ["dashboard"] }),
                  client.invalidateQueries({ queryKey: ["scenarios"] }),
                ]);
                toast.success("Scénář byl smazán.");
              })
            }
          >
            {busy ? "Mažu…" : "Smazat scénář"}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}

function PlusIcon() {
  return <Box data-icon="inline-start" />;
}
