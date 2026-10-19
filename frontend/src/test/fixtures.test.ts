import dayjs from "dayjs";
import { describe, expect, it } from "vitest";
import { wv } from "./fixtures";

describe("Test-Fixtures", () => {
  it("der Standard-Termin liegt in der Zukunft (sonst werden Tests mit der Zeit rot)", () => {
    expect(dayjs(wv().due_date).isAfter(dayjs(), "day")).toBe(true);
  });
});
