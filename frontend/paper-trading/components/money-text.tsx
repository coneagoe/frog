import { formatMoney } from "@/lib/format";

export function MoneyText({ value }: { value: string | number | null | undefined }) {
  return <span className="numeric">{formatMoney(value)}</span>;
}
