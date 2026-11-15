import { AlertCircle } from "lucide-react";
import { Status } from "@/components/shared";
import { Badge } from "@/components/ui/badge";
import { format } from "@/lib/api";
import { translateMessage } from "@/lib/i18n";
import type { Simulation } from "@/types/domain";

export function TrainingSummary({
  training,
  terminal,
}: {
  training: NonNullable<Simulation["training_loop"]>;
  terminal: boolean;
}) {
  const last = training.last_result;
  let status = "Trénink zastaven";
  if (training.active) {
    status = "Probíhá";
    if (terminal) {
      status =
        training.finished_attempts === training.attempt
          ? "Připravuji další pokus"
          : "Ukládám zkušenosti";
    }
  }

  return (
    <section className="panel" aria-label="Opakovaný trénink">
      <div className="training-summary">
        <div className="training-group">
          <div className="training-heading">
            <h2>Opakovaný trénink</h2>
            <Badge
              variant="outline"
              className={
                training.active && !terminal ? "status-good" : "status-neutral"
              }
            >
              {status}
            </Badge>
          </div>
          <dl className="training-metrics">
            <div>
              <dt>Pokus</dt>
              <dd>{format(training.attempt)}</dd>
            </div>
            <div>
              <dt>Ukončené pokusy</dt>
              <dd>{format(training.finished_attempts)}</dd>
            </div>
            <div>
              <dt>Nejvíce hotových úkolů</dt>
              <dd>{last ? format(training.best_completed_tasks) : "—"}</dd>
            </div>
          </dl>
        </div>
        <div className="training-group">
          <div className="training-heading">
            <h2>Poslední pokus</h2>
            {last && <Status value={last.status} />}
          </div>
          <dl className="training-metrics">
            <div>
              <dt>Hotové úkoly</dt>
              <dd>{last ? format(last.completed_tasks) : "—"}</dd>
            </div>
            <div>
              <dt>Kroky</dt>
              <dd>{last ? format(last.ticks) : "—"}</dd>
            </div>
            <div>
              <dt>Aktualizace vah</dt>
              <dd>{last ? format(last.model_updates) : "—"}</dd>
            </div>
          </dl>
        </div>
      </div>
      {last?.error && (
        <p className="training-reason">
          <AlertCircle aria-hidden="true" size={14} />
          <span>{translateMessage(last.error)}</span>
        </p>
      )}
    </section>
  );
}
