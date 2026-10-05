/// <reference types="node" />
/**
 * Findet alle uebersetzbaren Texte im Quellcode: t("..."), tk("..."), i18n.t("...") und
 * <Trans i18nKey="..." />. Mit {count} = Mehrzahl (i18next waehlt dann _one/_few/_many/_other).
 * Genutzt vom Test i18n.test.ts (und zum Erzeugen der Liste fuer neue Uebersetzungen).
 */
import { readdirSync, readFileSync, statSync } from "node:fs";
import { join } from "node:path";

export interface Key {
  key: string;
  plural: boolean;
  files: string[];
}

const CALL = /(?:\bi18n\.t|\btk|(?<![\w.])t)\(\s*"((?:[^"\\]|\\.)*)"(\s*,\s*\{[^}]*\})?/g;
const TRANS = /i18nKey="((?:[^"\\]|\\.)*)"/g;

function files(dir: string): string[] {
  return readdirSync(dir).flatMap((name) => {
    const path = join(dir, name);
    if (statSync(path).isDirectory()) return files(path);
    const skip = /\.test\.tsx?$/.test(name) || path.includes("schema.d.ts") || /[\\/]i18n[\\/]/.test(path);
    return /\.(ts|tsx)$/.test(name) && !skip ? [path] : [];
  });
}

export function extractKeys(srcDir: string): Map<string, Key> {
  const keys = new Map<string, Key>();
  const add = (key: string, plural: boolean, file: string) => {
    const text = JSON.parse(`"${key}"`) as string;
    const entry = keys.get(text) ?? { key: text, plural: false, files: [] };
    entry.plural ||= plural;
    if (!entry.files.includes(file)) entry.files.push(file);
    keys.set(text, entry);
  };
  for (const file of files(srcDir)) {
    const source = readFileSync(file, "utf8");
    for (const m of source.matchAll(CALL)) add(m[1], /\bcount\b/.test(m[2] ?? ""), file);
    for (const m of source.matchAll(TRANS)) add(m[1], false, file);
  }
  return keys;
}

export const PLURAL_FORMS: Record<string, string[]> = {
  de: ["one", "other"],
  en: ["one", "other"],
  ru: ["one", "few", "many"],
};
