import { useMemo } from "react";
import { useCategories } from "../api/queries";

/** Kategorie-Namen nach ID - fuer Tabellen, Historie, Regeln. */
export function useCategoryNames(): (id?: string | null) => string {
  const { data } = useCategories();
  return useMemo(() => {
    const names = new Map((data ?? []).map((c) => [c.id, c.name]));
    return (id?: string | null) => (id ? (names.get(id) ?? "unbekannt") : "ohne Kategorie");
  }, [data]);
}

/** Auswahl-Liste fuer Mantine Select */
export function useCategoryOptions() {
  const { data } = useCategories();
  return useMemo(
    () =>
      (data ?? []).map((c) => ({ value: c.id, label: c.name })).sort((a, b) => a.label.localeCompare(b.label, "de")),
    [data],
  );
}
