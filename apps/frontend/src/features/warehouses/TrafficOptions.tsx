import { Labeled, Picker } from "@/components/shared";
import type { GeneratorOptions } from "@/types/learning";
export type TrafficSettings = Pick<
  GeneratorOptions,
  "bottlenecks" | "passage_width" | "passage_count" | "traffic"
>;
export function TrafficOptions({
  value,
  onChange,
}: {
  value: TrafficSettings;
  onChange: (value: TrafficSettings) => void;
}) {
  return (
    <>
      <div className="form-pair">
        <Labeled label="Průjezdy mezi částmi skladu">
          <Picker
            label="Průjezdy mezi částmi skladu"
            value={value.bottlenecks ? "narrow" : "open"}
            onChange={(v) =>
              onChange({ ...value, bottlenecks: v === "narrow" })
            }
            options={[
              { value: "open", label: "Otevřený sklad" },
              { value: "narrow", label: "Zúžené průjezdy" },
            ]}
          />
        </Labeled>
        <Labeled label="Směr přeprav">
          <Picker
            label="Směr přeprav"
            value={value.traffic}
            onChange={(v) =>
              onChange({ ...value, traffic: v as TrafficSettings["traffic"] })
            }
            options={[
              { value: "one_way", label: "Zleva doprava" },
              { value: "bidirectional", label: "Oba směry" },
            ]}
          />
        </Labeled>
      </div>
      {value.bottlenecks && (
        <div className="form-pair">
          <Labeled label="Počet průjezdů">
            <Picker
              label="Počet průjezdů"
              value={String(value.passage_count)}
              onChange={(v) => onChange({ ...value, passage_count: Number(v) })}
              options={[1, 2, 3].map((n) => ({
                value: String(n),
                label: String(n),
              }))}
            />
          </Labeled>
          <Labeled label="Šířka průjezdu">
            <Picker
              label="Šířka průjezdu"
              value={String(value.passage_width)}
              onChange={(v) => onChange({ ...value, passage_width: Number(v) })}
              options={[1, 2, 3].map((n) => ({
                value: String(n),
                label: `${n} ${n === 1 ? "buňka" : "buňky"}`,
              }))}
            />
          </Labeled>
        </div>
      )}
      {value.bottlenecks && (
        <p className="subtle">
          Části skladu propojí pouze zvolené průjezdy. Úzká místa a protisměrné
          jízdy mohou způsobit čekání nebo selhání plánování.
        </p>
      )}
    </>
  );
}
