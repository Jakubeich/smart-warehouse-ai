import {
  counted,
  displayName,
  toolLabels,
  robotPropertyLabels,
} from "@/lib/i18n";
import { useRef, useState } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { useNavigate } from "react-router-dom";
import {
  Download,
  Upload,
  Save,
  Undo2,
  Redo2,
  Plus,
  MousePointer2,
  Trash2,
  Play,
} from "lucide-react";
import {
  Button,
  PageHeader,
  Picker,
  Labeled,
  ErrorPanel,
  useAction,
  EmptyState,
} from "@/components/shared";
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogDescription,
  DialogTrigger,
} from "@/components/ui/dialog";
import { FieldGroup } from "@/components/ui/field";
import { Input } from "@/components/ui/input";
import { api, post, download } from "@/lib/api";
import {
  scenarioSchema,
  defaultConfig,
  newRobot,
  newTask,
  type Scenario,
  type Cell,
  type Point,
} from "@/types/domain";
import { WarehouseCanvas } from "@/renderers/2d/WarehouseCanvas";
import { createRun } from "@/features/simulation/actions";
import { toast } from "sonner";
import { GeneratorDialog } from "@/features/warehouses/GeneratorDialog";
export default function Warehouses() {
  const q = useQuery({
    queryKey: ["scenarios"],
    queryFn: () => api<Scenario[]>("/scenarios"),
  });
  const client = useQueryClient();
  const navigate = useNavigate();
  const { act, busy, error } = useAction();
  const [scene, setScene] = useState<Scenario | null>(null);
  const [past, setPast] = useState<Scenario[]>([]);
  const [future, setFuture] = useState<Scenario[]>([]);
  const [tool, setTool] = useState("SELECT");
  const [hover, setHover] = useState<Point | null>(null);
  const [selected, setSelected] = useState<string | null>(null);
  const [newOpen, setNewOpen] = useState(false);
  const [name, setName] = useState("Můj sklad");
  const [width, setWidth] = useState(20);
  const [height, setHeight] = useState(14);
  const file = useRef<HTMLInputElement>(null);
  const edit = (next: Scenario) => {
    if (scene) setPast((p) => [...p.slice(-49), scene]);
    setFuture([]);
    setScene(next);
  };
  const load = (next: Scenario) => {
    setScene(structuredClone(next));
    setPast([]);
    setFuture([]);
    setSelected(null);
  };
  const paint = (p: Point) => {
    if (!scene) return;
    const robot = scene.robots.find(
      (r) => r.position[0] === p[0] && r.position[1] === p[1],
    );
    if (tool === "SELECT") {
      setSelected(robot?.id ?? null);
      return;
    }
    const next = structuredClone(scene);
    const cell = next.warehouse.cells.find((c) => c.x === p[0] && c.y === p[1]);
    if (tool === "ROBOT") {
      if (
        robot ||
        (cell && ["SHELF", "WALL", "OBSTACLE"].includes(cell.type))
      ) {
        toast.error("Robota lze umístit jen na volnou průchozí buňku.");
        return;
      }
      next.robots.push(newRobot(`R-${crypto.randomUUID().slice(0, 4)}`, p));
    } else if (tool === "ERASE" && robot) {
      next.robots = next.robots.filter((r) => r.id !== robot.id);
    } else {
      const type = (tool === "ERASE" ? "FLOOR" : tool) as Cell["type"];
      if (robot && ["WALL", "SHELF", "OBSTACLE"].includes(type)) {
        toast.error("Před zablokováním buňky přesuňte nebo odeberte robota.");
        return;
      }
      if (cell?.type === type) return;
      next.warehouse.cells = next.warehouse.cells.filter(
        (c) => c.x !== p[0] || c.y !== p[1],
      );
      if (type !== "FLOOR")
        next.warehouse.cells.push({ x: p[0], y: p[1], type });
    }
    edit(next);
  };
  const save = async () => {
    if (!scene) return;
    const saved = await post<Scenario>("/scenarios", scene);
    setScene(saved);
    await client.invalidateQueries();
    toast.success("Scénář byl uložen do PostgreSQL");
  };
  const robot = scene?.robots.find((r) => r.id === selected);
  return (
    <>
      <PageHeader
        title="Editor skladu"
        description="Upravte mapu a roboty a uložte scénář pro opakované simulace."
      >
        <GeneratorDialog
          onGenerated={(next) => {
            edit(next);
            setSelected(null);
            toast.success(
              "Mapa je připravená v editoru. Pro trvalé uložení zvolte Uložit scénář.",
            );
          }}
        />
        <Button variant="outline" onClick={() => file.current?.click()}>
          <Upload data-icon="inline-start" />
          Importovat JSON
        </Button>
        <Dialog open={newOpen} onOpenChange={setNewOpen}>
          <DialogTrigger asChild>
            <Button>
              <Plus data-icon="inline-start" />
              Nový sklad
            </Button>
          </DialogTrigger>
          <DialogContent>
            <DialogHeader>
              <DialogTitle>Vytvořit nový sklad</DialogTitle>
              <DialogDescription>
                Nová mapa obsahuje jednoho robota, nabíjecí stanici, nakládku a
                vykládku.
              </DialogDescription>
            </DialogHeader>
            <form
              onSubmit={(e) => {
                e.preventDefault();
                const id = crypto.randomUUID();
                const home: Point = [1, height - 2];
                load({
                  schema_version: 1,
                  id,
                  name,
                  warehouse: {
                    schema_version: 1,
                    id: `map-${id}`,
                    name,
                    width,
                    height,
                    cell_size: 1,
                    metadata: {},
                    cells: [
                      { x: 1, y: height - 2, type: "CHARGER" },
                      { x: 1, y: 1, type: "PICKUP" },
                      { x: width - 2, y: 1, type: "DROPOFF" },
                    ],
                  },
                  robots: [newRobot("R-01", home)],
                  tasks: [newTask("T-001", [1, 1], [width - 2, 1])],
                  seed: 42,
                  config: defaultConfig,
                });
                setNewOpen(false);
              }}
            >
              <FieldGroup>
                <Labeled label="Název">
                  <Input
                    aria-label="Název skladu"
                    value={name}
                    onChange={(e) => setName(e.target.value)}
                    required
                    maxLength={120}
                  />
                </Labeled>
                <Labeled label="Šířka (4–64 buněk)">
                  <Input
                    aria-label="Šířka"
                    type="number"
                    min={4}
                    max={64}
                    value={width}
                    onChange={(e) => setWidth(Number(e.target.value))}
                  />
                </Labeled>
                <Labeled label="Výška (4–64 buněk)">
                  <Input
                    aria-label="Výška"
                    type="number"
                    min={4}
                    max={64}
                    value={height}
                    onChange={(e) => setHeight(Number(e.target.value))}
                  />
                </Labeled>
                <Button type="submit">Vytvořit sklad</Button>
              </FieldGroup>
            </form>
          </DialogContent>
        </Dialog>
      </PageHeader>
      <input
        ref={file}
        hidden
        type="file"
        accept="application/json,.json"
        onChange={(e) => {
          const f = e.target.files?.[0];
          if (f)
            void act(async () => {
              if (f.size > 2_000_000)
                throw new Error("Soubor JSON musí být menší než 2 MB");
              load(scenarioSchema.parse(JSON.parse(await f.text())));
              toast.success(
                "Scénář byl importován. Pro trvalé uložení jej uložte.",
              );
            });
          e.target.value = "";
        }}
      />
      <ErrorPanel error={error || q.error} />
      <div className="panel editor-toolbar">
        <Picker
          label="Načíst scénář"
          value={scene?.id ?? ""}
          options={(q.data ?? []).map((s) => ({
            value: s.id,
            label: displayName(s.name),
          }))}
          onChange={(id) => {
            const next = q.data?.find((s) => s.id === id);
            if (next) load(next);
          }}
        />
        <Button
          variant="outline"
          size="icon"
          aria-label="Zpět"
          disabled={!past.length}
          onClick={() => {
            if (scene) {
              setFuture((f) => [scene, ...f]);
              setScene(past.at(-1)!);
              setPast((p) => p.slice(0, -1));
            }
          }}
        >
          <Undo2 />
        </Button>
        <Button
          variant="outline"
          size="icon"
          aria-label="Znovu"
          disabled={!future.length}
          onClick={() => {
            if (scene) {
              setPast((p) => [...p, scene]);
              setScene(future[0]);
              setFuture((f) => f.slice(1));
            }
          }}
        >
          <Redo2 />
        </Button>
        <span className="toolbar-spacer" />
        <Button
          variant="outline"
          disabled={!scene}
          onClick={() => scene && download(scene, `${scene.name}.json`)}
        >
          <Download data-icon="inline-start" />
          Exportovat JSON
        </Button>
        <Button disabled={!scene || busy} onClick={() => void act(save)}>
          <Save data-icon="inline-start" />
          Uložit scénář
        </Button>
        <Button
          variant="outline"
          disabled={!scene || busy}
          onClick={() =>
            void act(async () => {
              await save();
              if (scene) {
                await createRun(scene.id);
                navigate("/simulation");
              }
            })
          }
        >
          <Play data-icon="inline-start" />
          Otevřít simulaci
        </Button>
      </div>
      {!scene ? (
        <section className="panel">
          <EmptyState
            title="Otevřete nebo vytvořte sklad"
            description="Načtěte uložený scénář nebo vytvořte nový sklad. Při uložení se zkontroluje mapa i roboti."
          />
        </section>
      ) : (
        <div className="editor-workspace">
          <aside className="panel tool-panel">
            <div className="panel-heading">
              <h2>Nástroje editoru</h2>
            </div>
            {[
              "SELECT",
              "FLOOR",
              "WALL",
              "SHELF",
              "PICKUP",
              "DROPOFF",
              "CHARGER",
              "OBSTACLE",
              "ROBOT",
              "ERASE",
            ].map((t) => (
              <button
                key={t}
                onClick={() => setTool(t)}
                aria-pressed={tool === t}
              >
                {t === "SELECT" ? (
                  <MousePointer2 size={16} />
                ) : t === "ERASE" ? (
                  <Trash2 size={16} />
                ) : (
                  <i className={`tool-swatch ${t.toLowerCase()}`} />
                )}
                <span>{toolLabels[t]}</span>
              </button>
            ))}
            <p className="tool-help">
              Kreslete kliknutím nebo tažením. Pravým tlačítkem posouvejte mapu,
              kolečkem přibližujte. Při uložení se ověří pozice robotů a
              dostupnost stanic.
            </p>
          </aside>
          <section className="panel map-panel">
            <div className="panel-heading">
              <h2>{displayName(scene.name)}</h2>
              <span className="subtle">
                {hover
                  ? `Buňka ${hover.join(", ")} · ${toolLabels[scene.warehouse.cells.find((c) => c.x === hover[0] && c.y === hover[1])?.type ?? "FLOOR"]}`
                  : "Najeďte na buňku pro detail"}
              </span>
            </div>
            <WarehouseCanvas
              frame={{
                warehouse: scene.warehouse,
                robots: scene.robots,
                selectedRobot: selected,
                hover,
              }}
              editing
              paintDrag={!["SELECT", "ROBOT", "ERASE"].includes(tool)}
              onCell={paint}
              onHover={setHover}
            />
            <div className="map-legend">
              {scene.warehouse.width} × {scene.warehouse.height} buněk ·{" "}
              {counted(scene.robots.length, "robot")} ·{" "}
              {counted(scene.tasks.length, "task")}
              {scene.warehouse.metadata.shelf_coverage &&
                ` · regály ${Math.round(Number(scene.warehouse.metadata.shelf_coverage) * 100)} % · seed ${scene.seed}`}
            </div>
          </section>
          <aside className="panel editor-properties">
            <div className="panel-heading">
              <h2>{robot ? "Vlastnosti robota" : "Vlastnosti scénáře"}</h2>
            </div>
            <FieldGroup>
              {robot ? (
                <>
                  <Labeled label="Jméno robota">
                    <Input
                      aria-label="Jméno robota"
                      value={robot.name}
                      onChange={(e) =>
                        edit({
                          ...scene,
                          robots: scene.robots.map((r) =>
                            r.id === robot.id
                              ? { ...r, name: e.target.value }
                              : r,
                          ),
                        })
                      }
                    />
                  </Labeled>
                  {(["capacity", "battery", "battery_capacity"] as const).map(
                    (k) => (
                      <Labeled label={robotPropertyLabels[k]} key={k}>
                        <Input
                          aria-label={robotPropertyLabels[k]}
                          type="number"
                          min={0}
                          max={10000}
                          value={robot[k]}
                          onChange={(e) =>
                            edit({
                              ...scene,
                              robots: scene.robots.map((r) =>
                                r.id === robot.id
                                  ? { ...r, [k]: Number(e.target.value) }
                                  : r,
                              ),
                            })
                          }
                        />
                      </Labeled>
                    ),
                  )}
                  <Button
                    variant="outline"
                    onClick={() => {
                      edit({
                        ...scene,
                        robots: scene.robots.filter((r) => r.id !== robot.id),
                      });
                      setSelected(null);
                    }}
                  >
                    Odebrat robota
                  </Button>
                </>
              ) : (
                <>
                  <Labeled label="Název scénáře">
                    <Input
                      aria-label="Název scénáře"
                      value={displayName(scene.name)}
                      onChange={(e) =>
                        edit({
                          ...scene,
                          name: e.target.value,
                          warehouse: {
                            ...scene.warehouse,
                            name: e.target.value,
                          },
                        })
                      }
                    />
                  </Labeled>
                  <Labeled label="Velikost buňky (m)">
                    <Input
                      type="number"
                      min={0.1}
                      max={10}
                      step={0.1}
                      aria-label="Velikost buňky"
                      value={scene.warehouse.cell_size}
                      onChange={(e) =>
                        edit({
                          ...scene,
                          warehouse: {
                            ...scene.warehouse,
                            cell_size: Number(e.target.value),
                          },
                        })
                      }
                    />
                  </Labeled>
                  <Labeled label="Náhodný seed">
                    <Input
                      aria-label="Náhodný seed"
                      type="number"
                      min={0}
                      value={scene.seed}
                      onChange={(e) =>
                        edit({ ...scene, seed: Number(e.target.value) })
                      }
                    />
                  </Labeled>
                  <p className="subtle">
                    Vyberte robota pro změnu jména, baterie nebo nosnosti.
                  </p>
                  <Button
                    variant="outline"
                    onClick={() => {
                      const p = scene.warehouse.cells.find(
                          (c) => c.type === "PICKUP",
                        ),
                        d = scene.warehouse.cells.find(
                          (c) => c.type === "DROPOFF",
                        );
                      if (p && d)
                        edit({
                          ...scene,
                          tasks: [
                            ...scene.tasks,
                            newTask(
                              `T-${crypto.randomUUID().slice(0, 5)}`,
                              [p.x, p.y],
                              [d.x, d.y],
                            ),
                          ],
                        });
                      else
                        toast.error(
                          "Nejprve umístěte stanice nakládky a vykládky.",
                        );
                    }}
                  >
                    Přidat počáteční úkol
                  </Button>
                  <Button
                    variant="outline"
                    disabled={!scene.tasks.length}
                    onClick={() =>
                      edit({ ...scene, tasks: scene.tasks.slice(0, -1) })
                    }
                  >
                    Odebrat poslední úkol
                  </Button>
                </>
              )}
            </FieldGroup>
          </aside>
        </div>
      )}
    </>
  );
}
