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

  it("keeps stock names single-line with a compact width", () => {
    expect(globalsCss).toContain(".stock-name {");
    expect(globalsCss).toContain("display: block;");
    expect(globalsCss).toContain("max-width: 220px;");
    expect(globalsCss).toContain("overflow: hidden;");
    expect(globalsCss).toContain("text-overflow: ellipsis;");
    expect(globalsCss).toContain("white-space: nowrap;");
    expect(globalsCss).toContain(".stock-name--compact {");
    expect(globalsCss).toContain("max-width: 140px;");
  });
});
