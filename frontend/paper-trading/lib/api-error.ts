export class ApiError extends Error {
  constructor(
    public readonly status: number,
    public readonly code: string,
    message: string,
    public readonly details?: unknown
  ) {
    super(message);
    this.name = "ApiError";
  }
}

export async function parseApiError(response: Response): Promise<ApiError> {
  try {
    const payload = await response.json();
    if (payload && typeof payload === "object" && !Array.isArray(payload)) {
      const errorPayload = payload as { code?: unknown; message?: unknown; details?: unknown; detail?: unknown };
      const detail = errorPayload.detail ?? errorPayload.details;
      return new ApiError(
        response.status,
        typeof errorPayload.code === "string" ? errorPayload.code : "HTTP_ERROR",
        typeof errorPayload.message === "string" ? errorPayload.message : formatDetail(detail) ?? response.statusText,
        detail
      );
    }
    return new ApiError(response.status, "HTTP_ERROR", typeof payload === "string" ? payload : response.statusText);
  } catch {
    return new ApiError(response.status, "HTTP_ERROR", response.statusText || "Request failed");
  }
}

function formatDetail(detail: unknown): string | undefined {
  if (typeof detail === "string") return detail;
  if (Array.isArray(detail)) {
    const messages = detail.map(formatDetail).filter((message): message is string => Boolean(message));
    return messages.length ? messages.join("; ") : undefined;
  }
  if (detail && typeof detail === "object") {
    const objectDetail = detail as { loc?: unknown; msg?: unknown };
    if (typeof objectDetail.msg === "string") {
      const location = Array.isArray(objectDetail.loc) ? objectDetail.loc.join(".") : undefined;
      return location ? `${location}: ${objectDetail.msg}` : objectDetail.msg;
    }
    return Object.entries(detail)
      .map(([key, value]) => `${key}: ${typeof value === "string" ? value : JSON.stringify(value)}`)
      .join(", ");
  }
  return undefined;
}
