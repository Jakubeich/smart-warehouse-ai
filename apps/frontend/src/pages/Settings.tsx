import { errorText } from "@/lib/i18n";
import { useState } from "react";
import { toast } from "sonner";
import { Input } from "@/components/ui/input";
import { FieldGroup } from "@/components/ui/field";
import { Button, PageHeader, Labeled } from "@/components/shared";
import { usePreferences } from "@/stores/simulation";
import { configSchema, defaultConfig } from "@/types/domain";
export default function Settings() {
  const preferences = usePreferences();
  const [draft, setDraft] = useState(preferences.config);
  return (
    <>
      <PageHeader
        title="Nastavení aplikace"
        description="Výchozí hodnoty pro nové simulace. Běžící simulace si ponechají své nastavení."
      />
      <section className="panel settings-panel">
        <div className="panel-heading">
          <h2>Energie a čas simulace</h2>
        </div>
        <form
          onSubmit={(e) => {
            e.preventDefault();
            const parsed = configSchema.safeParse(draft);
            if (parsed.success) {
              preferences.setConfig(parsed.data);
              toast.success("Výchozí nastavení pro nové simulace bylo uloženo");
            } else toast.error(errorText(parsed.error));
          }}
        >
          <FieldGroup>
            <div className="form-pair">
              {(
                [
                  {
                    key: "move_energy",
                    label: "Spotřeba při pohybu",
                    min: 0,
                    max: 10,
                  },
                  {
                    key: "wait_energy",
                    label: "Spotřeba za krok čekání",
                    min: 0,
                    max: 1,
                  },
                  {
                    key: "handling_energy",
                    label: "Spotřeba za krok manipulace",
                    min: 0,
                    max: 10,
                  },
                  {
                    key: "charging_rate",
                    label: "Dobití za krok",
                    min: 0.01,
                    max: 100,
                  },
                  {
                    key: "critical_threshold",
                    label: "Energetická rezerva",
                    min: 0,
                    max: 100,
                  },
                  {
                    key: "tick_seconds",
                    label: "Simulované sekundy na krok",
                    min: 0.01,
                    max: 60,
                  },
                ] as const
              ).map((x) => (
                <Labeled label={x.label} key={x.key}>
                  <Input
                    aria-label={x.label}
                    type="number"
                    step={0.01}
                    min={x.min}
                    max={x.max}
                    value={draft[x.key]}
                    onChange={(e) =>
                      setDraft({ ...draft, [x.key]: Number(e.target.value) })
                    }
                  />
                </Labeled>
              ))}
            </div>
            <div className="inline-actions">
              <Button type="submit">Uložit nastavení</Button>
              <Button
                variant="outline"
                type="button"
                onClick={() => {
                  setDraft(defaultConfig);
                  preferences.setConfig(defaultConfig);
                  toast.success("Výchozí nastavení bylo obnoveno");
                }}
              >
                Obnovit výchozí hodnoty
              </Button>
            </div>
          </FieldGroup>
        </form>
      </section>
      <section className="panel settings-panel">
        <div className="panel-heading">
          <h2>Lokální prostředí</h2>
        </div>
        <div className="settings-info">
          <p>
            Diskrétní pohyb ve čtyřech směrech. Stav simulace řídí server.
            Protokol snímků stavu verze 1.
          </p>
          <p>
            Scénáře a výsledky experimentů se ukládají do PostgreSQL. Aktivní
            simulace jsou v paměti serveru a po jeho restartu se ztratí.
          </p>
          <a href="http://localhost:8000/docs" target="_blank" rel="noreferrer">
            Otevřít dokumentaci API ↗
          </a>
        </div>
      </section>
    </>
  );
}
