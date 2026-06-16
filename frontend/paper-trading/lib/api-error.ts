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
    return new ApiError(response.status, payload.code ?? "HTTP_ERROR", payload.message ?? response.statusText, payload.details);
  } catch {
    return new ApiError(response.status, "HTTP_ERROR", response.statusText || "Request failed");
  }
}
