import { labelStatus } from "@/lib/format";

export function StatusBadge({ value }: { value: string }) {
  return <span className={`status-badge status-badge--${value}`}>{labelStatus(value)}</span>;
}
