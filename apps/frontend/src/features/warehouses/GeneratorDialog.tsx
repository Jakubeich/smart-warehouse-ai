import { useState } from "react";
import { Shuffle, Dices } from "lucide-react";
import {
  Button,
  Labeled,
  Picker,
  ErrorPanel,
  useAction,
} from "@/components/shared";
import {
  Dialog,
  DialogTrigger,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogDescription,
} from "@/components/ui/dialog";
import { FieldGroup } from "@/components/ui/field";
import { Input } from "@/components/ui/input";
import { post } from "@/lib/api";
import { scenarioSchema, type Scenario } from "@/types/domain";
import { TrafficOptions } from "./TrafficOptions";
import { defaultGenerator } from "@/types/learning";
export function GeneratorDialog({
  onGenerated,
}: {
  onGenerated: (scene: Scenario) => void;
}) {
  const [open, setOpen] = useState(false);
  const [options, setOptions] = useState(defaultGenerator);
  const { act, busy, error } = useAction();
  return (
    <Dialog open={open} onOpenChange={setOpen}>
      <DialogTrigger asChild>
        <Button variant="outline">
          <Dices data-icon="inline-start" />
          Generovat sklad
        </Button>
      </DialogTrigger>
      <DialogContent className="max-h-[90vh] overflow-y-auto sm:max-w-xl">
        <DialogHeader>
          <DialogTitle>Generátor skladu</DialogTitle>
          <DialogDescription>
            Vytvořte mapu s průchozími uličkami, stanicemi, roboty a úkoly.
            Stejné parametry a seed vytvoří stejný scénář.
          </DialogDescription>
        </DialogHeader>
        <form
          onSubmit={(e) => {
            e.preventDefault();
            void act(async () => {
              const scene = scenarioSchema.parse(
                await post("/generator", options),
              );
              onGenerated(scene);
              setOpen(false);
            });
          }}
        >
          <FieldGroup>
            <Labeled label="Název">
              <Input
                aria-label="Název generovaného skladu"
                value={options.name}
                required
                maxLength={100}
                onChange={(e) =>
                  setOptions({ ...options, name: e.target.value })
                }
              />
            </Labeled>
            <div className="form-pair">
              <Labeled label="Šířka (12–64)">
                <Input
                  aria-label="Šířka generovaného skladu"
                  type="number"
                  min={12}
                  max={64}
                  required
                  value={options.width}
                  onChange={(e) =>
                    setOptions({ ...options, width: Number(e.target.value) })
                  }
                />
              </Labeled>
              <Labeled label="Výška (10–64)">
                <Input
                  aria-label="Výška generovaného skladu"
                  type="number"
                  min={10}
                  max={64}
                  required
                  value={options.height}
                  onChange={(e) =>
                    setOptions({ ...options, height: Number(e.target.value) })
                  }
                />
              </Labeled>
            </div>
            <Labeled label="Rozložení regálů">
              <Picker
                label="Rozložení regálů"
                value={options.layout}
                onChange={(v) =>
                  setOptions({ ...options, layout: v as typeof options.layout })
                }
                options={[
                  { value: "aisles", label: "Dlouhé řady" },
                  { value: "islands", label: "Regálové ostrůvky" },
                  { value: "mixed", label: "Smíšené rozložení" },
                ]}
              />
            </Labeled>
            <Labeled label="Cílové pokrytí regály (%)">
              <Input
                aria-label="Cílové pokrytí regály"
                type="number"
                min={0}
                max={40}
                required
                value={Math.round(options.density * 100)}
                onChange={(e) =>
                  setOptions({
                    ...options,
                    density: Number(e.target.value) / 100,
                  })
                }
              />
            </Labeled>
            <p className="subtle">
              Průchody mají přednost před hustotou. Skutečné pokrytí uvidíte v
              náhledu.
            </p>
            <div className="form-pair">
              <Labeled label="Roboti (1–32)">
                <Input
                  aria-label="Počet generovaných robotů"
                  type="number"
                  min={1}
                  max={32}
                  required
                  value={options.robot_count}
                  onChange={(e) =>
                    setOptions({
                      ...options,
                      robot_count: Number(e.target.value),
                    })
                  }
                />
              </Labeled>
              <Labeled label="Úkoly (1–200)">
                <Input
                  aria-label="Počet generovaných úkolů"
                  type="number"
                  min={1}
                  max={200}
                  required
                  value={options.task_count}
                  onChange={(e) =>
                    setOptions({
                      ...options,
                      task_count: Number(e.target.value),
                    })
                  }
                />
              </Labeled>
            </div>
            <TrafficOptions
              value={options}
              onChange={(v) => setOptions({ ...options, ...v })}
            />
            <Labeled label="Seed">
              <div className="inline-actions">
                <Input
                  aria-label="Seed generátoru"
                  type="number"
                  min={0}
                  max={4294967295}
                  required
                  value={options.seed}
                  onChange={(e) =>
                    setOptions({ ...options, seed: Number(e.target.value) })
                  }
                />
                <Button
                  type="button"
                  variant="outline"
                  aria-label="Náhodný seed"
                  onClick={() =>
                    setOptions({
                      ...options,
                      seed: crypto.getRandomValues(new Uint32Array(1))[0],
                    })
                  }
                >
                  <Shuffle />
                </Button>
              </div>
            </Labeled>
            <ErrorPanel error={error} />
            <Button type="submit" disabled={busy}>
              {busy ? "Generuji…" : "Vygenerovat náhled"}
            </Button>
            <p className="subtle">
              Náhled otevře editor. Scénář můžete upravit, uložit a spustit ve
              2D i 3D. Dokončené přepravy rozšiřují data pro trénink.
            </p>
          </FieldGroup>
        </form>
      </DialogContent>
    </Dialog>
  );
}
