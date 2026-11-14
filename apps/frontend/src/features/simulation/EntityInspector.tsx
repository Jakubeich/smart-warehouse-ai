import { counted } from "@/lib/i18n";
import { Battery, MapPin } from "lucide-react";
import { Button, EmptyState, Status } from "@/components/shared";
import { format } from "@/lib/api";
import { robotColors } from "@/renderers/shared/scene";
import type { Simulation } from "@/types/domain";
export function EntityInspector({
  simulation: s,
  selectedRobot,
  selectedTask,
  busy,
  execute,
}: {
  simulation: Simulation;
  selectedRobot: string | null;
  selectedTask: string | null;
  busy: boolean;
  execute: (action: string, body?: unknown) => void;
}) {
  const robot = s.robots.find((r) => r.id === selectedRobot);
  const task = s.tasks.find((t) => t.id === selectedTask);
  return (
    <div className="entity-details">
      {robot ? (
        <>
          <div className="inspector-identity">
            <i
              style={{
                background:
                  robotColors[s.robots.indexOf(robot) % robotColors.length],
              }}
            />
            <div>
              <h3>{robot.id}</h3>
              <small>{robot.name}</small>
            </div>
            <Status value={robot.status} />
          </div>
          <div className="inspector-section">
            <div className="detail-row">
              <span>
                <Battery size={15} />
                Baterie
              </span>
              <strong>
                {format((robot.battery / robot.battery_capacity) * 100)}%
              </strong>
            </div>
            <div className="battery-track">
              <i
                style={{
                  width: `${(robot.battery / robot.battery_capacity) * 100}%`,
                }}
              />
            </div>
            <div className="detail-row">
              <span>
                <MapPin size={15} />
                Pozice
              </span>
              <strong>({robot.position.join(", ")})</strong>
            </div>
            <div className="detail-row">
              <span>Úkol</span>
              <strong>{robot.task_id ?? "Nepřiřazeno"}</strong>
            </div>
            <div className="detail-row">
              <span>Cíl</span>
              <strong>{robot.goal?.join(", ") ?? "—"}</strong>
            </div>
            <div className="detail-row">
              <span>Zbývající trasa</span>
              <strong>
                {counted(
                  Math.max(0, robot.path.length - robot.path_index - 1),
                  "tick",
                )}
              </strong>
            </div>
          </div>
          <div className="inspector-section">
            <h4>Výkon</h4>
            <div className="detail-row">
              <span>Vzdálenost</span>
              <strong>
                {format(robot.distance * s.warehouse.cell_size, 2)} m
              </strong>
            </div>
            <div className="detail-row">
              <span>Čekání</span>
              <strong>{counted(robot.waiting, "tick")}</strong>
            </div>
            <div className="detail-row">
              <span>Doručené úkoly</span>
              <strong>{robot.completed_tasks}</strong>
            </div>
            <div className="detail-row">
              <span>Náklad / nosnost</span>
              <strong>
                {format(robot.load, 2)} / {format(robot.capacity, 2)} kg
              </strong>
            </div>
            <Button
              variant="outline"
              size="sm"
              disabled={busy || !["IDLE", "OFFLINE"].includes(robot.mode)}
              onClick={() =>
                execute(`robots/${robot.id}/availability`, {
                  available: robot.mode === "OFFLINE",
                })
              }
            >
              {robot.mode === "OFFLINE" ? "Zapnout robota" : "Vyřadit robota"}
            </Button>
          </div>
        </>
      ) : task ? (
        <div className="inspector-section">
          <h3>{task.id}</h3>
          <Status value={task.status} />
          {[
            ["Nakládka", task.pickup.join(", ")],
            ["Vykládka", task.dropoff.join(", ")],
            ["Přiřazený robot", task.assigned_robot ?? "Ve frontě"],
            ["Priorita", task.priority],
            ["Náklad", `${format(task.payload_weight, 2)} kg`],
            ["Krok vytvoření", task.created_tick],
            ["Krok dokončení", task.completed_tick ?? "—"],
          ].map(([label, value]) => (
            <div className="detail-row" key={label}>
              <span>{label}</span>
              <strong>{value}</strong>
            </div>
          ))}
        </div>
      ) : (
        <EmptyState
          title="Vyberte robota nebo úkol"
          description="Výběrem robota nebo úkolu zobrazíte jeho aktuální stav."
        />
      )}
    </div>
  );
}
