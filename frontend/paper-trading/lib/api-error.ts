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
      const errorPayload = payload as { code?: unknown; message?: unknown; details?: unknown };
      return new ApiError(
        response.status,
        typeof errorPayload.code === "string" ? errorPayload.code : "HTTP_ERROR",
        typeof errorPayload.message === "string" ? errorPayload.message : response.statusText,
        errorPayload.details
      );
    }
    return new ApiError(response.status, "HTTP_ERROR", typeof payload === "string" ? payload : response.statusText);
  } catch {
    return new ApiError(response.status, "HTTP_ERROR", response.statusText || "Request failed");
  }
}
