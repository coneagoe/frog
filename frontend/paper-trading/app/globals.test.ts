import { readFileSync } from "node:fs";
import { join } from "node:path";
import { describe, expect, it } from "vitest";

const globalsCss = readFileSync(join(process.cwd(), "app/globals.css"), "utf8");

describe("global page layout CSS", () => {
  it("keeps the page header account control in a stable right column", () => {
    expect(globalsCss).toContain("grid-template-columns: minmax(0, 1fr) auto;");
    expect(globalsCss).toContain(".page__header > div");
    expect(globalsCss).toContain(".page__header > label");
    expect(globalsCss).toContain(".page__header select");
  });
});
