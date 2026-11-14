import { errorText } from "@/lib/i18n";
import { useState, type ReactNode } from "react";
import { AlertCircle, LoaderCircle, type LucideIcon } from "lucide-react";
import { toast } from "sonner";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import { Field, FieldLabel } from "@/components/ui/field";
import {
  Empty,
  EmptyHeader,
  EmptyTitle,
  EmptyDescription,
} from "@/components/ui/empty";
import {
  Select,
  SelectContent,
  SelectGroup,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { human } from "@/lib/api";
export function Picker({
  value,
  onChange,
  options,
  label,
  disabled = false,
}: {
  value: string;
  onChange: (v: string) => void;
  options: { value: string; label: string }[];
  label: string;
  disabled?: boolean;
}) {
  return (
    <Select value={value} onValueChange={onChange} disabled={disabled}>
      <SelectTrigger aria-label={label}>
        <SelectValue placeholder={label} />
      </SelectTrigger>
      <SelectContent>
        <SelectGroup>
          {options.map((o) => (
            <SelectItem key={o.value} value={o.value}>
              {o.label}
            </SelectItem>
          ))}
        </SelectGroup>
      </SelectContent>
    </Select>
  );
}
export function Labeled({
  label,
  children,
}: {
  label: string;
  children: ReactNode;
}) {
  return (
    <Field>
      <FieldLabel>{label}</FieldLabel>
      {children}
    </Field>
  );
}
export function Status({ value }: { value: string }) {
  const tone = [
    "RUNNING",
    "COMPLETED",
    "SUCCESS",
    "IDLE",
    "READY",
    "connected",
  ].includes(value)
    ? "good"
    : ["FAILED", "ERROR", "CONFLICT", "UNSOLVABLE"].includes(value)
      ? "bad"
      : "neutral";
  return (
    <Badge variant="outline" className={`status-${tone}`}>
      {human(value)}
    </Badge>
  );
}
export function PageHeader({
  title,
  description,
  children,
}: {
  title: string;
  description: string;
  children?: ReactNode;
}) {
  return (
    <header className="page-header">
      <div>
        <h1>{title}</h1>
        <p>{description}</p>
      </div>
      <div className="header-actions">{children}</div>
    </header>
  );
}
export function EmptyState({
  title,
  description,
  children,
}: {
  title: string;
  description: string;
  children?: ReactNode;
}) {
  return (
    <Empty>
      <EmptyHeader>
        <EmptyTitle>{title}</EmptyTitle>
        <EmptyDescription>{description}</EmptyDescription>
      </EmptyHeader>
      {children}
    </Empty>
  );
}
export function ErrorPanel({ error }: { error: unknown }) {
  if (!error) return null;
  return (
    <Alert variant="destructive">
      <AlertCircle />
      <AlertTitle>Požadavek se nepodařilo dokončit</AlertTitle>
      <AlertDescription>{errorText(error)}</AlertDescription>
    </Alert>
  );
}
export function Metric({
  label,
  value,
  unit,
  icon: Icon,
  tone = "cyan",
}: {
  label: string;
  value: ReactNode;
  unit?: string;
  icon: LucideIcon;
  tone?: string;
}) {
  return (
    <div className="metric">
      <div className={`metric-icon ${tone}`}>
        <Icon size={22} />
      </div>
      <div>
        <span>{label}</span>
        <strong>
          {value} {unit && <small>{unit}</small>}
        </strong>
      </div>
    </div>
  );
}
export function useAction() {
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  async function act(fn: () => Promise<unknown>) {
    setBusy(true);
    setError(null);
    try {
      await fn();
    } catch (e) {
      const message = errorText(e);
      setError(message);
      toast.error(message);
    } finally {
      setBusy(false);
    }
  }
  return { busy, error, act };
}
export function Loading() {
  return (
    <div className="loading">
      <LoaderCircle className="spin" /> Načítání aplikace…
    </div>
  );
}
export { Button };
