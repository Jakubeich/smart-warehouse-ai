import { useState } from "react";
import { Plus } from "lucide-react";
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
import {
  Button,
  Labeled,
  Picker,
  useAction,
  ErrorPanel,
} from "@/components/shared";
import { useSimulation } from "@/stores/simulation";
import { control } from "@/features/simulation/actions";
import { newTask, type Point } from "@/types/domain";
export function TaskDialog() {
  const s = useSimulation((x) => x.simulation);
  const [open, setOpen] = useState(false);
  const [pickup, setPickup] = useState("");
  const [dropoff, setDropoff] = useState("");
  const [priority, setPriority] = useState(1);
  const [weight, setWeight] = useState(10);
  const [loadDuration, setLoadDuration] = useState(2);
  const [unloadDuration, setUnloadDuration] = useState(2);
  const { busy, error, act } = useAction();
  if (!s) return null;
  const options = (type: string) =>
    s.warehouse.cells
      .filter((c) => c.type === type)
      .map((c) => ({
        value: `${c.x},${c.y}`,
        label: `${type === "PICKUP" ? "Nakládka" : "Vykládka"} (${c.x}, ${c.y})`,
      }));
  const point = (v: string): Point => {
    const [x, y] = v.split(",").map(Number);
    return [x, y];
  };
  return (
    <Dialog open={open} onOpenChange={setOpen}>
      <DialogTrigger asChild>
        <Button variant="outline" size="sm">
          <Plus data-icon="inline-start" />
          Přidat úkol
        </Button>
      </DialogTrigger>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>Vytvořit přepravní úkol</DialogTitle>
          <DialogDescription>
            Přidejte přepravu do aktuální simulace. Přiřazovací algoritmus
            vybere vhodného robota.
          </DialogDescription>
        </DialogHeader>
        <form
          onSubmit={(e) => {
            e.preventDefault();
            void act(async () => {
              await control("tasks", {
                ...newTask(
                  `T-${crypto.randomUUID().slice(0, 8)}`,
                  point(pickup || options("PICKUP")[0]?.value),
                  point(dropoff || options("DROPOFF")[0]?.value),
                  priority,
                ),
                payload_weight: weight,
                load_duration: loadDuration,
                unload_duration: unloadDuration,
              });
              setOpen(false);
            });
          }}
        >
          <FieldGroup>
            <Labeled label="Stanice nakládky">
              <Picker
                label="Stanice nakládky"
                value={pickup || options("PICKUP")[0]?.value || ""}
                options={options("PICKUP")}
                onChange={setPickup}
              />
            </Labeled>
            <Labeled label="Stanice vykládky">
              <Picker
                label="Stanice vykládky"
                value={dropoff || options("DROPOFF")[0]?.value || ""}
                options={options("DROPOFF")}
                onChange={setDropoff}
              />
            </Labeled>
            <Labeled label="Priorita (1–10)">
              <Input
                aria-label="Priorita"
                type="number"
                min={1}
                max={10}
                value={priority}
                onChange={(e) => setPriority(Number(e.target.value))}
                required
              />
            </Labeled>
            <div className="form-pair">
              <Labeled label="Náklad (kg)">
                <Input
                  aria-label="Hmotnost nákladu"
                  type="number"
                  min={0.1}
                  max={10000}
                  step={0.1}
                  value={weight}
                  onChange={(e) => setWeight(Number(e.target.value))}
                  required
                />
              </Labeled>
              <Labeled label="Nakládka (kroky)">
                <Input
                  aria-label="Doba nakládky"
                  type="number"
                  min={1}
                  max={100}
                  value={loadDuration}
                  onChange={(e) => setLoadDuration(Number(e.target.value))}
                  required
                />
              </Labeled>
              <Labeled label="Vykládka (kroky)">
                <Input
                  aria-label="Doba vykládky"
                  type="number"
                  min={1}
                  max={100}
                  value={unloadDuration}
                  onChange={(e) => setUnloadDuration(Number(e.target.value))}
                  required
                />
              </Labeled>
            </div>
            <ErrorPanel error={error} />
            <Button
              type="submit"
              disabled={
                busy || !options("PICKUP").length || !options("DROPOFF").length
              }
            >
              Vytvořit úkol
            </Button>
          </FieldGroup>
        </form>
      </DialogContent>
    </Dialog>
  );
}
