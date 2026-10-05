/** Anzeige-Formate und Bezeichnungen - in der Sprache der Oberflaeche (src/i18n). */
import dayjs from "dayjs";
import i18n, { intlLocale } from "../i18n";

const t = (key: string, options?: Record<string, unknown>) => i18n.t(key, options);
/** Markiert Texte, die erst spaeter mit t() uebersetzt werden (fuer die Vollstaendigkeitspruefung). */
export const tk = <T extends string>(text: T): T => text;

export function formatDate(value?: string | null): string {
  if (!value) return "–";
  const d = dayjs(value);
  if (!d.isValid()) return "–";
  return new Intl.DateTimeFormat(intlLocale(), { day: "2-digit", month: "2-digit", year: "numeric" }).format(
    d.toDate(),
  );
}

export function formatDateTime(value?: string | null): string {
  if (!value) return "–";
  const d = dayjs(value);
  if (!d.isValid()) return "–";
  return new Intl.DateTimeFormat(intlLocale(), {
    day: "2-digit",
    month: "2-digit",
    year: "numeric",
    hour: "2-digit",
    minute: "2-digit",
  }).format(d.toDate());
}

export function formatAmount(value?: number | null): string {
  if (value === null || value === undefined) return "–";
  return new Intl.NumberFormat(intlLocale(), { style: "currency", currency: "EUR" }).format(value);
}

export function formatPercent(value?: number | null): string {
  if (value === null || value === undefined) return "";
  return new Intl.NumberFormat(intlLocale(), { style: "percent", maximumFractionDigits: 0 }).format(value);
}

/** "heute", "morgen", "in 5 Tagen", "seit 3 Tagen ueberfaellig" - relativ zu today. */
export function relativeDue(due: string, today: dayjs.Dayjs = dayjs()): { label: string; overdue: boolean } {
  const days = dayjs(due).startOf("day").diff(today.startOf("day"), "day");
  if (days === 0) return { label: t("heute"), overdue: false };
  if (days === 1) return { label: t("morgen"), overdue: false };
  if (days > 1) return { label: t("in {{count}} Tagen", { count: days }), overdue: false };
  if (days === -1) return { label: t("seit gestern überfällig"), overdue: true };
  return { label: t("seit {{count}} Tagen überfällig", { count: -days }), overdue: true };
}

export function formatMonths(months: number): string {
  const years = Math.floor(months / 12);
  const rest = months % 12;
  const parts = [];
  if (years) parts.push(t("{{count}} Jahre", { count: years }));
  if (rest) parts.push(t("{{count}} Monate", { count: rest }));
  return parts.join(" ") || t("{{count}} Monate", { count: 0 });
}

const CLASSIFICATION: Record<string, { label: string; color: string }> = {
  pending: { label: tk("wird eingeordnet"), color: "gray" },
  auto_assigned: { label: tk("automatisch"), color: "blue" },
  needs_review: { label: tk("zu prüfen"), color: "orange" },
  confirmed: { label: tk("bestätigt"), color: "green" },
};
export function classificationInfo(status: string): { label: string; color: string } {
  const info = CLASSIFICATION[status];
  return info ? { label: t(info.label), color: info.color } : { label: status, color: "gray" };
}

const STAGES: Record<string, string> = {
  embedding: tk("Beispielvergleich"),
  llm: tk("Sprachmodell"),
  manual: tk("manuell"),
  chat: tk("Chat"),
};
export function stageLabel(stage?: string | null): string | null {
  if (!stage) return null;
  return STAGES[stage] ? t(STAGES[stage]) : stage;
}

const RECURRENCES: Record<string, string> = {
  none: tk("einmalig"),
  monthly: tk("monatlich"),
  yearly: tk("jährlich"),
  custom_months: tk("alle X Monate"),
};
export function recurrenceOptions(): { value: string; label: string }[] {
  return Object.entries(RECURRENCES).map(([value, label]) => ({ value, label: t(label) }));
}

export function recurrenceText(recurrence: string, months?: number | null): string {
  if (recurrence === "custom_months" && months) return t("alle {{count}} Monate", { count: months });
  return RECURRENCES[recurrence] ? t(RECURRENCES[recurrence]) : recurrence;
}

const SOURCES: Record<string, string> = {
  manual: tk("manuell"),
  ai_suggested: tk("KI"),
  retention_rule: tk("Aufbewahrung"),
};
export function sourceLabel(source: string): string {
  return SOURCES[source] ? t(SOURCES[source]) : source;
}

const ORIGINALS: Record<string, string> = {
  ja: tk("Original vorhanden"),
  nein: tk("kein Original"),
  unbekannt: tk("unbekannt"),
};
export function originalOptions(): { value: string; label: string }[] {
  return Object.entries(ORIGINALS).map(([value, label]) => ({ value, label: t(label) }));
}

// Einheitliche Bezeichnungen der KI-Fristen (backend/homedms/ai/extraction.py, _CANONICAL_LABELS)
const NOTE_LABELS = new Set<string>([
  tk("Kündigungsfrist"),
  tk("Widerspruchsfrist"),
  tk("Zahlungsfrist"),
  tk("Vertragsende"),
  tk("TÜV-Termin"),
  tk("Prüftermin"),
  tk("Frist"),
]);
// Text der Aufbewahrungs-Termine (backend/homedms/core/wiedervorlage.py, retention_note)
const RETENTION_NOTE =
  /^Aufbewahrungsfrist \((.+), (?:(\d+) Jahre?)? ?(?:(\d+) Monate?)?\) endet - Dokument kann danach vernichtet werden\.( Das Papier-Original muss bis dahin aufbewahrt werden\.)?$/;

/** Bezeichnung eines Termins in der Sprache der Oberflaeche (eigene Texte bleiben, wie sie sind). */
export function noteLabel(note?: string | null): string {
  if (!note) return "";
  if (NOTE_LABELS.has(note)) return t(note);
  const m = RETENTION_NOTE.exec(note);
  if (m) {
    const months = Number(m[2] ?? 0) * 12 + Number(m[3] ?? 0);
    const text = t("Aufbewahrungsfrist ({{category}}, {{duration}}) endet – Dokument kann danach vernichtet werden.", {
      category: t(m[1]),
      duration: formatMonths(months),
    });
    return m[4] ? `${text} ${t("Das Papier-Original muss bis dahin aufbewahrt werden.")}` : text;
  }
  return note;
}

/** Ist das Dokument noch in der automatischen Verarbeitung? (dann regelmaessig neu laden) */
export function isProcessing(doc: {
  ocr_status: string;
  classification_status: string;
  extraction_status: string;
}): boolean {
  return doc.ocr_status === "pending" || doc.classification_status === "pending" || doc.extraction_status === "pending";
}
