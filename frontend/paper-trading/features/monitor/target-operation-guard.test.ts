import { describe, expect, it } from "vitest";
import { TargetOperationGuard } from "./target-operation-guard";

describe("TargetOperationGuard", () => {
  it("rejects duplicate same-target operations while allowing another target", () => {
    const guard = new TargetOperationGuard();

    expect(guard.begin(17)).toBe(true);
    expect(guard.begin(17)).toBe(false);
    expect(guard.begin(18)).toBe(true);
  });
});
