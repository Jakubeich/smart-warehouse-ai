import {
  counted,
  displayName,
  layerLabels,
  searchText,
} from "@/lib/i18n";
import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { Link } from "react-router-dom";
import {
  Battery,
  ChevronDown,
  Download,
  Layers as LayersIcon,
  Pause,
  Play,
  Repeat,
  RotateCcw,
  SkipForward,
  Square,
} from "lucide-react";
import {
  Button,
  PageHeader,
  Picker,
  ErrorPanel,
  EmptyState,
  Status,
  useAction,
} from "@/components/shared";
import { Input } from "@/components/ui/input";
import {
  Sheet,
  SheetContent,
  SheetHeader,
  SheetTitle,
  SheetDescription,
} from "@/components/ui/sheet";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import {
  DropdownMenu,
  DropdownMenuTrigger,
  DropdownMenuContent,
  DropdownMenuGroup,
  DropdownMenuCheckboxItem,
  DropdownMenuSeparator,
  DropdownMenuLabel,
} from "@/components/ui/dropdown-menu";
import { api, download, format, human } from "@/lib/api";
import { type Scenario, type Point } from "@/types/domain";
import {
  usePreferences,
  useSimulation,
  type Layers,
} from "@/stores/simulation";
import { createRun, control } from "@/features/simulation/actions";
import { EntityInspector } from "@/features/simulation/EntityInspector";
import { RunDetails } from "@/features/simulation/RunDetails";
import { TrainingSummary } from "@/features/simulation/TrainingSummary";
import { WarehouseViewport } from "@/renderers/WarehouseViewport";
import { robotColors } from "@/renderers/shared/scene";
import { TaskDialog } from "@/features/tasks/TaskDialog";
import { cn } from "@/lib/utils";

export default function SimulationPage() {
  const s = useSimulation((x) => x.simulation);
  const selected = useSimulation((x) => x.selectedRobot);
  const selectedTask = useSimulation((x) => x.selectedTask);
  const connection = useSimulation((x) => x.connection);
  const preferences = usePreferences();
  const { busy, error, act } = useAction();
  const [filter, setFilter] = useState("");
  const [obstacle, setObstacle] = useState(false);
  const [hover, setHover] = useState<Point | null>(null);
  const [inspector, setInspector] = useState(false);
  const scenes = useQuery({
    queryKey: ["scenarios"],
    queryFn: () => api<Scenario[]>("/scenarios"),
  });
  const scenarioOptions = (scenes.data ?? []).map((scene) => ({
    value: scene.id,
    label: displayName(scene.name),
  }));
  if (s && !scenarioOptions.some((option) => option.value === s.scenario_id)) {
    scenarioOptions.unshift({
      value: s.scenario_id,
      label: displayName(s.name),
    });
  }
  const terminal = !!s && ["COMPLETED", "FAILED", "STOPPED"].includes(s.status);
  const training = s?.training_loop;
  const trainingActive = training?.active ?? false;
  const execute = (action: string, body?: unknown) =>
    void act(() => control(action, body));
  const selectRobot = (id: string) => {
    useSimulation.getState().selectRobot(id);
    setInspector(true);
  };
  const selectTask = (id: string) => {
    useSimulation.getState().selectTask(id);
    setInspector(true);
  };
  const matches = (value: string) =>
    searchText(value).includes(searchText(filter));
  return (
    <>
      <PageHeader
        title="Živá simulace"
        description={
          s
            ? `${displayName(s.warehouse.name)} · ${counted(s.robots.length, "robot")} · ${counted(s.tasks.length, "task")}`
            : "Vyberte scénář a spusťte simulaci."
        }
      >
        <div className="inline-actions">
          <Button
            variant={trainingActive ? "outline" : "default"}
            disabled={!s || busy}
            onClick={() =>
              execute(trainingActive ? "training-stop" : "training-start")
            }
          >
            {trainingActive ? (
              <Square data-icon="inline-start" />
            ) : (
              <Repeat data-icon="inline-start" />
            )}
            {trainingActive ? "Zastavit trénink" : "Spustit opakovaný trénink"}
          </Button>
          <Button
            variant="outline"
            disabled={!s}
            onClick={() => s && download(s, `simulation-${s.id}.json`)}
          >
            <Download data-icon="inline-start" />
            Exportovat běh
          </Button>
        </div>
      </PageHeader>
      <ErrorPanel error={error || scenes.error || (!trainingActive && s?.error)} />
      {s && connection !== "connected" && (
        <p className="connection-notice" role="status">
          {connection === "connecting"
            ? "Obnovování spojení se simulací…"
            : "Spojení bylo přerušeno. Probíhá další pokus…"}
        </p>
      )}
      <div className="simulation-toolbar panel">
        <div className="scenario-picker">
          <Picker
            label="Scénář skladu"
            value={s?.scenario_id ?? ""}
            options={scenarioOptions}
            onChange={(id) => void act(() => createRun(id))}
            disabled={busy}
          />
        </div>
        <Status value={s?.status ?? "READY"} />
        <div className="tick-readout">
          <span>Krok</span>
          <strong data-testid="tick">{s?.tick ?? 0}</strong>
        </div>
        <div className="toolbar-buttons">
          <Picker
            label="Rychlost simulace"
            value={String(s?.speed ?? 1)}
            options={[0.25, 0.5, 1, 2, 4, 8, 16, 32, 64, 128, 256, 512].map((v) => ({
              value: String(v),
              label: `${format(v, 2)}×`,
            }))}
            onChange={(v) => execute("speed", { speed: Number(v) })}
            disabled={!s || busy}
          />
          <Button
            variant="outline"
            size="icon"
            aria-label="Obnovit simulaci"
            title="Obnovit simulaci"
            disabled={!s || busy || trainingActive}
            onClick={() => execute("reset")}
          >
            <RotateCcw />
          </Button>
          <Button
            variant="outline"
            disabled={
              !s || busy || trainingActive || s.status === "RUNNING" || terminal
            }
            onClick={() => execute("step")}
          >
            <SkipForward data-icon="inline-start" />
            Krok
          </Button>
          <Button
            disabled={!s || busy || trainingActive || terminal}
            onClick={() => execute(s?.status === "RUNNING" ? "pause" : "start")}
          >
            {s?.status === "RUNNING" ? (
              <Pause data-icon="inline-start" />
            ) : (
              <Play data-icon="inline-start" />
            )}
            {s?.status === "RUNNING" ? "Pozastavit" : "Spustit"}
          </Button>
        </div>
      </div>
      {training && <TrainingSummary training={training} terminal={terminal} />}
      {!s ? (
        <section className="panel">
          <EmptyState
            title="Nejprve vyberte sklad"
            description="Vyberte uložený scénář nebo vytvořte nový v editoru skladu."
          >
            <Button asChild variant="outline">
              <Link to="/warehouses">Otevřít editor skladu</Link>
            </Button>
          </EmptyState>
        </section>
      ) : (
        <>
          <section className="panel simulation-workspace">
            <div className="workbench">
              <div className="map-panel">
                <div className="panel-heading viewport-heading">
                  <h2>
                    Mapa skladu{" "}
                    <span>
                      {s.warehouse.width} × {s.warehouse.height}
                    </span>
                  </h2>
                  <div className="viewport-actions">
                    <Tabs
                      value={preferences.viewMode}
                      onValueChange={(mode) =>
                        preferences.setViewMode(mode as "2d" | "3d")
                      }
                    >
                      <TabsList aria-label="Zobrazení skladu">
                        <TabsTrigger
                          value="2d"
                          aria-controls="warehouse-viewport"
                        >
                          2D
                        </TabsTrigger>
                        <TabsTrigger
                          value="3d"
                          aria-controls="warehouse-viewport"
                        >
                          3D
                        </TabsTrigger>
                      </TabsList>
                    </Tabs>
                    <DropdownMenu>
                      <DropdownMenuTrigger asChild>
                        <Button variant="ghost" size="sm">
                          <LayersIcon data-icon="inline-start" />
                          Vrstvy
                          <ChevronDown data-icon="inline-end" />
                        </Button>
                      </DropdownMenuTrigger>
                      <DropdownMenuContent align="end" className="w-52">
                        <DropdownMenuGroup>
                          <DropdownMenuLabel>
                            Zobrazené vrstvy
                          </DropdownMenuLabel>
                          {(
                            Object.keys(preferences.layers) as (keyof Layers)[]
                          ).map((key) => (
                            <DropdownMenuCheckboxItem
                              key={key}
                              checked={preferences.layers[key]}
                              onSelect={(e) => e.preventDefault()}
                              onCheckedChange={() =>
                                preferences.toggleLayer(key)
                              }
                            >
                              {layerLabels[key]}
                            </DropdownMenuCheckboxItem>
                          ))}
                        </DropdownMenuGroup>
                        <DropdownMenuSeparator />
                        <DropdownMenuGroup>
                          <DropdownMenuCheckboxItem
                            checked={obstacle}
                            onCheckedChange={setObstacle}
                          >
                            Upravit překážky
                          </DropdownMenuCheckboxItem>
                        </DropdownMenuGroup>
                      </DropdownMenuContent>
                    </DropdownMenu>
                  </div>
                </div>
                {obstacle && (
                  <div className="map-edit-notice" role="status">
                    Kliknutím na buňku přidáte nebo odstraníte překážku.
                    <Button
                      variant="ghost"
                      size="sm"
                      onClick={() => setObstacle(false)}
                    >
                      Hotovo
                    </Button>
                  </div>
                )}
                <div
                  id="warehouse-viewport"
                  className="warehouse-viewport"
                  role="tabpanel"
                  aria-label={
                    preferences.viewMode === "3d" ? "3D pohled" : "2D pohled"
                  }
                >
                  <WarehouseViewport
                    frame={{
                      warehouse: s.warehouse,
                      robots: s.robots,
                      simulation: s,
                      selectedRobot: selected,
                      hover: obstacle ? hover : null,
                    }}
                    onHover={setHover}
                    onSelect={selectRobot}
                    editing={obstacle}
                    onCell={(p) => {
                      if (obstacle)
                        execute("obstacles", {
                          position: p,
                          remove: s.obstacles.some(
                            (o) => o[0] === p[0] && o[1] === p[1],
                          ),
                        });
                    }}
                  />
                </div>
                <div className="map-legend">
                  <span>
                    <i className="shelf" />
                    Regál
                  </span>
                  <span>
                    <i className="pickup" />
                    Nakládka
                  </span>
                  <span>
                    <i className="dropoff" />
                    Vykládka
                  </span>
                  <span>
                    <i className="charger" />
                    Nabíjení
                  </span>
                  <span>
                    <i className="route" />
                    Trasa
                  </span>
                </div>
              </div>
              <aside className="fleet-panel">
                <Tabs defaultValue="robots" onValueChange={() => setFilter("")}>
                  <div className="fleet-tabs">
                    <TabsList variant="line" className="w-full">
                      <TabsTrigger value="robots">
                        Roboti{" "}
                        <span className="tab-count">{s.robots.length}</span>
                      </TabsTrigger>
                      <TabsTrigger value="tasks">
                        Úkoly{" "}
                        <span className="tab-count">{s.tasks.length}</span>
                      </TabsTrigger>
                    </TabsList>
                  </div>
                  <div className="fleet-search">
                    <Input
                      aria-label="Filtrovat roboty nebo úkoly"
                      placeholder="Filtrovat podle ID nebo stavu…"
                      value={filter}
                      onChange={(e) => setFilter(e.target.value)}
                    />
                  </div>
                  <TabsContent value="robots" className="fleet-list">
                    {s.robots
                      .filter((r) =>
                        matches(
                          `${r.id} ${r.status} ${human(r.mode === "OFFLINE" ? "OFFLINE" : r.status)}`,
                        ),
                      )
                      .map((r) => (
                        <button
                          key={r.id}
                          className={cn(
                            "robot-row",
                            selected === r.id && "selected",
                          )}
                          onClick={() => selectRobot(r.id)}
                        >
                          <i
                            style={{
                              background:
                                robotColors[
                                  s.robots.indexOf(r) % robotColors.length
                                ],
                            }}
                          />
                          <div>
                            <strong>{r.id}</strong>
                            <small>
                              {human(
                                r.mode === "OFFLINE" ? "OFFLINE" : r.status,
                              )}
                            </small>
                          </div>
                          <span className="battery-label">
                            <Battery size={14} />
                            {format((r.battery / r.battery_capacity) * 100)}%
                          </span>
                        </button>
                      ))}
                    {!s.robots.some((r) =>
                      matches(
                        `${r.id} ${r.status} ${human(r.mode === "OFFLINE" ? "OFFLINE" : r.status)}`,
                      ),
                    ) && (
                      <p className="list-empty">
                        Žádní roboti neodpovídají filtru.
                      </p>
                    )}
                  </TabsContent>
                  <TabsContent value="tasks" className="fleet-list">
                    {s.tasks
                      .filter((t) =>
                        matches(`${t.id} ${t.status} ${human(t.status)}`),
                      )
                      .map((t) => (
                        <button
                          className={cn(
                            "task-row",
                            selectedTask === t.id && "selected",
                          )}
                          key={t.id}
                          onClick={() => selectTask(t.id)}
                        >
                          <strong>{t.id}</strong>
                          <small>
                            {human(t.status)} · Priorita {t.priority}
                          </small>
                        </button>
                      ))}
                    {!s.tasks.some((t) =>
                      matches(`${t.id} ${t.status} ${human(t.status)}`),
                    ) && (
                      <p className="list-empty">
                        Žádné úkoly neodpovídají filtru.
                      </p>
                    )}
                  </TabsContent>
                </Tabs>
                <div className="fleet-footer">
                  <TaskDialog />
                  <span className="subtle">
                    Kliknutím na řádek zobrazíte detail.
                  </span>
                </div>
              </aside>
            </div>
            <div className="simulation-summary">
              <div>
                <span>Úkoly</span>
                <strong>
                  {s.metrics.completed_tasks} / {s.tasks.length}
                </strong>
              </div>
              <div>
                <span>Vzdálenost</span>
                <strong>{format(s.metrics.total_distance)} m</strong>
              </div>
              <div>
                <span>Kolize</span>
                <strong>{s.metrics.executed_collisions}</strong>
              </div>
            </div>
          </section>
          <RunDetails simulation={s} />
          <Sheet open={inspector} onOpenChange={setInspector}>
            <SheetContent className="overflow-y-auto">
              <SheetHeader>
                <SheetTitle>
                  {selectedTask ? "Detail úkolu" : "Detail robota"}
                </SheetTitle>
                <SheetDescription>
                  Aktuální stav z probíhající simulace.
                </SheetDescription>
              </SheetHeader>
              <EntityInspector
                simulation={s}
                selectedRobot={selected}
                selectedTask={selectedTask}
                busy={busy}
                execute={execute}
              />
            </SheetContent>
          </Sheet>
        </>
      )}
    </>
  );
}
