import dayjs from "dayjs";
import { describe, expect, it } from "vitest";
import { formatAmount, formatDate, formatMonths, isProcessing, recurrenceText, relativeDue } from "./format";

describe("relativeDue", () => {
  const today = dayjs("2026-09-30T15:00:00");
  it.each([
    ["2026-09-30", "heute", false],
    ["2026-10-01", "morgen", false],
    ["2026-10-15", "in 15 Tagen", false],
    ["2026-09-29", "seit gestern überfällig", true],
    ["2026-09-20", "seit 10 Tagen überfällig", true],
  ])("%s -> %s", (due, label, overdue) => {
    expect(relativeDue(due, today)).toEqual({ label, overdue });
  });
});

describe("Formatierung", () => {
  it("Datum deutsch, leere Werte als Strich", () => {
    expect(formatDate("2026-10-15")).toBe("15.10.2026");
    expect(formatDate(null)).toBe("–");
    expect(formatDate("kein datum")).toBe("–");
  });

  it("Betrag in Euro", () => {
    expect(formatAmount(1234.5).replace(/\s/g, " ")).toBe("1.234,50 €");
    expect(formatAmount(0).replace(/\s/g, " ")).toBe("0,00 €");
    expect(formatAmount(null)).toBe("–");
  });

  it("Monate als Jahre und Monate", () => {
    expect(formatMonths(120)).toBe("10 Jahre");
    expect(formatMonths(12)).toBe("1 Jahr");
    expect(formatMonths(18)).toBe("1 Jahr 6 Monate");
    expect(formatMonths(1)).toBe("1 Monat");
  });

  it("Wiederholung", () => {
    expect(recurrenceText("custom_months", 3)).toBe("alle 3 Monate");
    expect(recurrenceText("yearly")).toBe("jährlich");
  });

  it("Verarbeitung laeuft, solange ein Schritt aussteht", () => {
    const done = { ocr_status: "done", classification_status: "confirmed", extraction_status: "done" };
    expect(isProcessing(done)).toBe(false);
    expect(isProcessing({ ...done, extraction_status: "pending" })).toBe(true);
    expect(isProcessing({ ...done, ocr_status: "failed" })).toBe(false);
  });
});
