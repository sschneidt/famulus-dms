/**
 * Mehrsprachigkeit (Deutsch, Englisch, Russisch) mit i18next.
 *
 * Schluessel sind die deutschen Texte selbst: t("Hochladen"). Fehlt eine Uebersetzung, erscheint
 * also der deutsche Text - nie ein technischer Schluessel. en.json/ru.json enthalten die
 * Uebersetzungen, de.json nur Mehrzahlformen ("{{count}} Dokumente_one"). Der Test
 * src/i18n/i18n.test.ts prueft, dass jeder t()-Text in allen Sprachen vorhanden ist.
 *
 * Die Sprache gehoert zur Person (Konto, auf dem Server gespeichert). Vor der Anmeldung gilt die
 * zuletzt gewaehlte bzw. die Browsersprache.
 */
import dayjs from "dayjs";
import "dayjs/locale/de";
import "dayjs/locale/en-gb";
import "dayjs/locale/ru";
import i18n from "i18next";
import { initReactI18next } from "react-i18next";
import de from "./de.json";
import en from "./en.json";
import ru from "./ru.json";

export const LANGUAGES = [
  { code: "de", label: "Deutsch" },
  { code: "en", label: "English" },
  { code: "ru", label: "Русский" },
] as const;
export type Language = (typeof LANGUAGES)[number]["code"];

const STORAGE_KEY = "homedms.language";
/** Fuer Intl (Datum, Betraege) - Englisch mit europaeischem Datumsformat */
const INTL_LOCALE: Record<Language, string> = { de: "de-DE", en: "en-GB", ru: "ru-RU" };
const DAYJS_LOCALE: Record<Language, string> = { de: "de", en: "en-gb", ru: "ru" };

export function isLanguage(value: unknown): value is Language {
  return LANGUAGES.some((l) => l.code === value);
}

function stored(): Language | null {
  try {
    const value = window.localStorage.getItem(STORAGE_KEY);
    return isLanguage(value) ? value : null;
  } catch {
    return null;
  }
}

/** Zuletzt gewaehlte Sprache, sonst die des Browsers, sonst Deutsch. */
export function detectLanguage(): Language {
  const chosen = stored();
  if (chosen) return chosen;
  const browser = typeof navigator !== "undefined" ? (navigator.languages ?? [navigator.language]) : [];
  for (const tag of browser) {
    const code = tag?.slice(0, 2).toLowerCase();
    if (isLanguage(code)) return code;
  }
  return "de";
}

void i18n.use(initReactI18next).init({
  resources: { de: { translation: de }, en: { translation: en }, ru: { translation: ru } },
  lng: "de",
  fallbackLng: false,
  keySeparator: false,
  nsSeparator: false,
  returnEmptyString: false,
  interpolation: { escapeValue: false }, // React schuetzt selbst
  react: { useSuspense: false },
});

function apply(lang: Language) {
  dayjs.locale(DAYJS_LOCALE[lang]);
  if (typeof document !== "undefined") document.documentElement.lang = lang;
}

/** Sprache umschalten. remember=true: auch fuer die Anmeldeseite merken. */
export async function setLanguage(lang: Language, remember = true): Promise<void> {
  if (remember) {
    try {
      window.localStorage.setItem(STORAGE_KEY, lang);
    } catch {
      /* privater Modus */
    }
  }
  apply(lang);
  await i18n.changeLanguage(lang);
}

export function currentLanguage(): Language {
  return isLanguage(i18n.language) ? i18n.language : "de";
}

export function intlLocale(): string {
  return INTL_LOCALE[currentLanguage()];
}

/** Eingabeformat fuer Datumsfelder (Mantine DateInput) */
export function dateInputFormat(): string {
  return currentLanguage() === "en" ? "DD/MM/YYYY" : "DD.MM.YYYY";
}

/** Trennzeichen fuer Betragsfelder (Mantine NumberInput) */
export function numberSeparators(): { decimalSeparator: string; thousandSeparator: string } {
  const lang = currentLanguage();
  if (lang === "en") return { decimalSeparator: ".", thousandSeparator: "," };
  if (lang === "ru") return { decimalSeparator: ",", thousandSeparator: " " };
  return { decimalSeparator: ",", thousandSeparator: "." };
}

export function dayjsLocale(): string {
  return DAYJS_LOCALE[currentLanguage()];
}

// Auf der Anmeldeseite gewaehlt: nach der Anmeldung ins Konto uebernehmen (sonst gilt die Sprache des Kontos)
let pendingChoice: Language | null = null;

export async function chooseLanguageBeforeLogin(lang: Language): Promise<void> {
  pendingChoice = lang;
  await setLanguage(lang);
}

export function takePendingChoice(): Language | null {
  const choice = pendingChoice;
  pendingChoice = null;
  return choice;
}

/** Beim Laden der Seite: gespeicherte bzw. Browsersprache aktivieren. */
export function initLanguage(): void {
  const lang = detectLanguage();
  apply(lang);
  void i18n.changeLanguage(lang);
}

export default i18n;
