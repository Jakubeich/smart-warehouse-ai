import { errorText, statusLabels, translateMessage } from "./i18n";
import { z } from "zod";
export class ApiError extends Error {
  constructor(message: string, readonly status: number) {
    super(message);
  }
}
export async function api<T>(path: string, options?: RequestInit): Promise<T> {
  const response = await fetch(`/api${path}`, {
    ...options,
    headers: { "Content-Type": "application/json", ...options?.headers },
  }).catch((error: unknown) => {
    throw new Error(errorText(error));
  });
  if (!response.ok) {
    const data: unknown = await response.json().catch(() => null);
    const parsed = z
      .object({ error: z.object({ message: z.string() }) })
      .safeParse(data);
    throw new ApiError(
      parsed.success
        ? translateMessage(parsed.data.error.message)
        : `Požadavek se nezdařil (HTTP ${response.status})`,
      response.status,
    );
  }
  if (response.status === 204) return undefined as T;
  return response.json() as Promise<T>;
}
export const post = <T>(path: string, body: unknown = {}) =>
  api<T>(path, { method: "POST", body: JSON.stringify(body) });
export function download(data: unknown, name: string) {
  const url = URL.createObjectURL(
    new Blob([JSON.stringify(data, null, 2)], { type: "application/json" }),
  );
  const link = document.createElement("a");
  link.href = url;
  link.download = name;
  link.click();
  URL.revokeObjectURL(url);
}
export const format = (n: number, digits = 0) =>
  new Intl.NumberFormat("cs-CZ", { maximumFractionDigits: digits }).format(n);
export const human = (s: string) => statusLabels[s.toUpperCase()] ?? s;
