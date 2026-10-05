import { useMemo } from "react";
import { useTranslation } from "react-i18next";
import type { Category } from "../api/client";
import { useCategories } from "../api/queries";
import { tk } from "./format";

// Basis-Kategorien (backend/homedms/schemas/setup.py) - erscheinen in der Sprache der Person,
// solange sie nicht umbenannt wurden. Ordnernamen in der Ablage bleiben deutsch.
export const DEFAULT_CATEGORY_NAMES = [
  tk("Rechnungen"),
  tk("Vertraege"),
  tk("Versicherungen"),
  tk("Bank & Finanzen"),
  tk("Steuern"),
  tk("Gesundheit & Medizinisches"),
  tk("Behoerden & Amtliches"),
  tk("Wohnen & Nebenkosten"),
  tk("Haus & Reparaturen"),
  tk("Fahrzeug"),
  tk("Arbeit & Gehalt"),
  tk("Bildung"),
  tk("Garantien & Kaufbelege"),
  tk("Sonstiges"),
];
const DEFAULTS = new Set<string>(DEFAULT_CATEGORY_NAMES);

/** Anzeigename einer Kategorie in der Sprache der Oberflaeche. */
export function useCategoryLabel(): (category: Pick<Category, "name" | "is_system_default">) => string {
  const { t } = useTranslation();
  return (c) => (c.is_system_default && DEFAULTS.has(c.name) ? t(c.name) : c.name);
}

/** Kategorie-Namen nach ID - fuer Tabellen, Historie, Regeln. */
export function useCategoryNames(): (id?: string | null) => string {
  const { data } = useCategories();
  const { t, i18n } = useTranslation();
  const label = useCategoryLabel();
  return useMemo(() => {
    const names = new Map((data ?? []).map((c) => [c.id, label(c)]));
    return (id?: string | null) => (id ? (names.get(id) ?? t("unbekannt")) : t("ohne Kategorie"));
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [data, i18n.language]);
}

/** Auswahl-Liste fuer Mantine Select */
export function useCategoryOptions() {
  const { data } = useCategories();
  const { i18n } = useTranslation();
  const label = useCategoryLabel();
  return useMemo(
    () =>
      (data ?? [])
        .map((c) => ({ value: c.id, label: label(c) }))
        .sort((a, b) => a.label.localeCompare(b.label, i18n.language)),
    // eslint-disable-next-line react-hooks/exhaustive-deps
    [data, i18n.language],
  );
}
