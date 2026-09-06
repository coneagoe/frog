import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";
import { ConditionEditor } from "./condition-editor";

describe("ConditionEditor", () => {
  it("emits deterministic payloads for every condition type", async () => {
    const onChange = vi.fn();
    render(<ConditionEditor condition={{ type: "price_threshold", direction: "above", value: 10 }} market="A" frequency="daily" onChange={onChange} />);

    const expected = [
      { type: "price_threshold", direction: "above", value: 0 },
      { type: "ma_cross", direction: "golden", fast: 5, slow: 20 },
      { type: "change_pct", direction: "above", value: 0 },
      { type: "price_cross_ma", direction: "above", period: 20 },
      { type: "close_cross_ma", direction: "above", period: 20 },
      { type: "rsi", direction: "above", value: 70, period: 14 }
    ];
    for (const condition of expected) {
      await userEvent.selectOptions(screen.getByLabelText("Condition type"), condition.type);
      expect(onChange).toHaveBeenLastCalledWith(condition);
    }
  });

  it("only offers close cross MA for daily A-share targets", () => {
    const { rerender } = render(<ConditionEditor condition={{ type: "price_threshold", direction: "above", value: 10 }} market="HK" frequency="daily" onChange={vi.fn()} />);
    expect(screen.queryByRole("option", { name: "Close crosses MA" })).not.toBeInTheDocument();
    rerender(<ConditionEditor condition={{ type: "price_threshold", direction: "above", value: 10 }} market="A" frequency="intraday" onChange={vi.fn()} />);
    expect(screen.queryByRole("option", { name: "Close crosses MA" })).not.toBeInTheDocument();
  });
});
