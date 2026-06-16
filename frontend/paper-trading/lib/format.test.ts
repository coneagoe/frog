import { describe, expect, it } from "vitest";
import { formatDate, formatMoney, formatQuantity, labelStatus } from "./format";

describe("formatMoney", () => {
  it("formats decimal strings as CNY money", () => {
    expect(formatMoney("123456.7")).toBe("¥123,456.70");
  });

  it("returns a dash for missing money", () => {
    expect(formatMoney(undefined)).toBe("-");
  });
});

describe("formatQuantity", () => {
  it("formats share quantities", () => {
    expect(formatQuantity(123400)).toBe("123,400");
  });
});

describe("formatDate", () => {
  it("keeps ISO dates readable", () => {
    expect(formatDate("2026-06-16")).toBe("2026-06-16");
  });
});

describe("labelStatus", () => {
  it("humanizes snake case statuses", () => {
    expect(labelStatus("partially_filled")).toBe("Partially Filled");
  });
});
