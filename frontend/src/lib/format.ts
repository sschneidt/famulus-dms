/** Anzeige-Formate und deutsche Bezeichnungen fuer die Oberflaeche. */
import dayjs from "dayjs";

export function formatDate(value?: string | null): string {
  if (!value) return "–";
  const d = dayjs(value);
  return d.isValid() ? d.format("DD.MM.YYYY") : "–";
}

export function formatDateTime(value?: string | null): string {
  if (!value) return "–";
  const d = dayjs(value);
  return d.isValid() ? d.format("DD.MM.YYYY, HH:mm") : "–";
}

const euro = new Intl.NumberFormat("de-DE", { style: "currency", currency: "EUR" });
export function formatAmount(value?: number | null): string {
  return value === null || value === undefined ? "–" : euro.format(value);
}

export function formatPercent(value?: number | null): string {
  return value === null || value === undefined ? "" : `${Math.round(value * 100)} %`;
}

/** "heute", "morgen", "in 5 Tagen", "seit 3 Tagen ueberfaellig" - relativ zu today. */
export function relativeDue(due: string, today: dayjs.Dayjs = dayjs()): { label: string; overdue: boolean } {
  const days = dayjs(due).startOf("day").diff(today.startOf("day"), "day");
  if (days === 0) return { label: "heute", overdue: false };
  if (days === 1) return { label: "morgen", overdue: false };
  if (days > 1) return { label: `in ${days} Tagen`, overdue: false };
  if (days === -1) return { label: "seit gestern überfällig", overdue: true };
  return { label: `seit ${-days} Tagen überfällig`, overdue: true };
}

export function formatMonths(months: number): string {
  const years = Math.floor(months / 12);
  const rest = months % 12;
  const parts = [];
  if (years) parts.push(`${years} ${years === 1 ? "Jahr" : "Jahre"}`);
  if (rest) parts.push(`${rest} ${rest === 1 ? "Monat" : "Monate"}`);
  return parts.join(" ") || "0 Monate";
}

export const classificationLabels: Record<string, { label: string; color: string }> = {
  pending: { label: "wird eingeordnet", color: "gray" },
  auto_assigned: { label: "automatisch", color: "blue" },
  needs_review: { label: "zu prüfen", color: "orange" },
  confirmed: { label: "bestätigt", color: "green" },
};

export const stageLabels: Record<string, string> = {
  embedding: "Beispielvergleich",
  llm: "Sprachmodell",
  manual: "manuell",
  chat: "Chat",
};

export const recurrenceLabels: Record<string, string> = {
  none: "einmalig",
  monthly: "monatlich",
  yearly: "jährlich",
  custom_months: "alle X Monate",
};

export function recurrenceText(recurrence: string, months?: number | null): string {
  if (recurrence === "custom_months" && months) return `alle ${months} Monate`;
  return recurrenceLabels[recurrence] ?? recurrence;
}

export const sourceLabels: Record<string, string> = {
  manual: "manuell",
  ai_suggested: "KI",
  retention_rule: "Aufbewahrung",
};

export const originalLabels: Record<string, string> = {
  ja: "Original vorhanden",
  nein: "kein Original",
  unbekannt: "unbekannt",
};

/** Ist das Dokument noch in der automatischen Verarbeitung? (dann regelmaessig neu laden) */
export function isProcessing(doc: {
  ocr_status: string;
  classification_status: string;
  extraction_status: string;
}): boolean {
  return doc.ocr_status === "pending" || doc.classification_status === "pending" || doc.extraction_status === "pending";
}
