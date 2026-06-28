const moneyFormatter = new Intl.NumberFormat("zh-CN", {
  style: "currency",
  currency: "CNY",
  minimumFractionDigits: 2,
  maximumFractionDigits: 2
});

const quantityFormatter = new Intl.NumberFormat("zh-CN");

export function formatMoney(value: string | number | null | undefined): string {
  if (value === null || value === undefined || value === "") {
    return "-";
  }
  const numericValue = typeof value === "number" ? value : Number(value);
  if (!Number.isFinite(numericValue)) {
    return "-";
  }
  return moneyFormatter.format(numericValue);
}

export function formatQuantity(value: number | null | undefined): string {
  if (value === null || value === undefined) {
    return "-";
  }
  return quantityFormatter.format(value);
}

export function formatPercent(value: string | number | null | undefined): string {
  if (value === null || value === undefined || value === "") {
    return "-";
  }
  const numericValue = typeof value === "number" ? value : Number(value);
  if (!Number.isFinite(numericValue)) {
    return "-";
  }
  return `${(numericValue * 100).toFixed(2)}%`;
}

export function formatBackendLabel(value: string | null | undefined): string {
  if (!value) {
    return "-";
  }
  return value
    .replaceAll("_", " ")
    .toLowerCase()
    .split(" ")
    .map((part) => part.charAt(0).toUpperCase() + part.slice(1))
    .join(" ");
}

export function formatDate(value: string | null | undefined): string {
  if (!value) {
    return "-";
  }
  return value.slice(0, 10);
}

export function labelStatus(value: string | null | undefined): string {
  if (!value) {
    return "-";
  }
  return value
    .split("_")
    .map((part) => part.charAt(0).toUpperCase() + part.slice(1))
    .join(" ");
}
