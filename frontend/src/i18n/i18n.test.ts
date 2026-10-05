/// <reference types="node" />
import { join } from "node:path";
import { describe, expect, it } from "vitest";
import de from "./de.json";
import en from "./en.json";
import { extractKeys, PLURAL_FORMS } from "./extract";
import ru from "./ru.json";

const catalogs: Record<string, Record<string, string>> = { de, en, ru };
const keys = [...extractKeys(join(process.cwd(), "src")).values()];

describe("Übersetzungen", () => {
  it("findet die Texte im Code", () => {
    expect(keys.length).toBeGreaterThan(300);
  });

  for (const lang of ["en", "ru"] as const) {
    it(`${lang}: jeder Text ist übersetzt`, () => {
      const catalog = catalogs[lang];
      const missing = keys.flatMap((k) =>
        k.plural
          ? PLURAL_FORMS[lang].map((f) => `${k.key}_${f}`).filter((x) => !catalog[x])
          : catalog[k.key]
            ? []
            : [k.key],
      );
      expect(missing).toEqual([]);
    });

    it(`${lang}: Platzhalter stimmen überein`, () => {
      const catalog = catalogs[lang];
      const wrong = Object.entries(catalog).filter(([key, value]) => {
        const base = key.replace(/_(one|few|many|other)$/, "");
        const expected = new Set(base.match(/\{\{\w+\}\}/g) ?? []);
        const actual = new Set(value.match(/\{\{\w+\}\}/g) ?? []);
        expected.delete("{{count}}");
        actual.delete("{{count}}");
        return [...expected].some((p) => !actual.has(p)) || [...actual].some((p) => !expected.has(p));
      });
      expect(wrong).toEqual([]);
    });
  }

  it("de: Mehrzahlformen vorhanden", () => {
    const missing = keys
      .filter((k) => k.plural)
      .flatMap((k) => PLURAL_FORMS.de.map((f) => `${k.key}_${f}`).filter((x) => !de[x as keyof typeof de]));
    expect(missing).toEqual([]);
  });
});
