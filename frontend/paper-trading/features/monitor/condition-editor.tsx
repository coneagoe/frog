import type { MonitorCondition, MonitorFrequency, MonitorMarket } from "@/lib/types";

type Props = {
  condition: MonitorCondition;
  market: MonitorMarket;
  frequency: MonitorFrequency;
  onChange: (condition: MonitorCondition) => void;
};

const defaults: Record<MonitorCondition["type"], MonitorCondition> = {
  price_threshold: { type: "price_threshold", direction: "above", value: 0 },
  ma_cross: { type: "ma_cross", direction: "golden", fast: 5, slow: 20 },
  change_pct: { type: "change_pct", direction: "above", value: 0 },
  price_cross_ma: { type: "price_cross_ma", direction: "above", period: 20 },
  close_cross_ma: { type: "close_cross_ma", direction: "above", period: 20 },
  rsi: { type: "rsi", direction: "above", value: 70, period: 14 }
};

export function ConditionEditor({ condition, market, frequency, onChange }: Props) {
  const closeCrossAllowed = market === "A" && frequency === "daily";
  const types = Object.keys(defaults) as MonitorCondition["type"][];
  const setNumber = (key: string, value: string) => onChange({ ...condition, [key]: Number(value) } as MonitorCondition);

  return <fieldset className="form__fieldset monitor-condition"><legend>Condition</legend>
    <label>Condition type
      <select aria-label="Condition type" value={condition.type} onChange={(event) => onChange(defaults[event.target.value as MonitorCondition["type"]])}>
        {types.filter((type) => type !== "close_cross_ma" || closeCrossAllowed).map((type) => <option key={type} value={type}>{({ price_threshold: "Price threshold", ma_cross: "MA cross", change_pct: "Change percentage", price_cross_ma: "Price crosses MA", close_cross_ma: "Close crosses MA", rsi: "RSI" })[type]}</option>)}
      </select>
    </label>
    {condition.type === "ma_cross" ? <><label>Direction<select aria-label="Direction" value={condition.direction} onChange={(event) => onChange({ ...condition, direction: event.target.value as "golden" | "death" })}><option value="golden">Golden</option><option value="death">Death</option></select></label><label>Fast period<input aria-label="Fast period" type="number" value={condition.fast} onChange={(event) => setNumber("fast", event.target.value)} /></label><label>Slow period<input aria-label="Slow period" type="number" value={condition.slow} onChange={(event) => setNumber("slow", event.target.value)} /></label></> : <ConditionFields condition={condition} setNumber={setNumber} onChange={onChange} />}
  </fieldset>;
}

function ConditionFields({ condition, setNumber, onChange }: { condition: Exclude<MonitorCondition, { type: "ma_cross" }>; setNumber: (key: string, value: string) => void; onChange: (condition: MonitorCondition) => void }) {
  const hasDirection = condition.type !== "close_cross_ma";
  const valueLabel = condition.type === "rsi" ? "RSI value" : condition.type === "change_pct" ? "Change percentage" : "Value";
  return <>{hasDirection ? <label>Direction<select aria-label="Direction" value={condition.direction} onChange={(event) => onChange({ ...condition, direction: event.target.value as "above" | "below" })}><option value="above">Above</option><option value="below">Below</option></select></label> : null}
    {"value" in condition ? <label>{valueLabel}<input aria-label={valueLabel} type="number" value={condition.value} onChange={(event) => setNumber("value", event.target.value)} /></label> : null}
    {"period" in condition ? <label>Period<input aria-label="Period" type="number" value={condition.period} onChange={(event) => setNumber("period", event.target.value)} /></label> : null}
  </>;
}
