/** Same-origin JSON client. The backend owns authorization; the browser never holds keys. */

export class ApiError extends Error {
  readonly status: number;
  constructor(message: string, status: number) {
    super(message);
    this.name = "ApiError";
    this.status = status;
  }
}

export const DEFAULT_TIMEOUT_MS = 90_000;

export async function detailOf(response: Response): Promise<string> {
  const data = await response.json().catch(() => null);
  if (typeof data?.detail === "string") return data.detail;
  if (response.status === 401) return "Tu sesión ha caducado. Vuelve a iniciar sesión.";
  if (response.status >= 500)
    return `El servidor no pudo completar la solicitud (${response.status}).`;
  return `Solicitud fallida (${response.status})`;
}

export async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(path, {
    ...init,
    signal: init?.signal ?? AbortSignal.timeout(DEFAULT_TIMEOUT_MS),
  });
  if (!response.ok) throw new ApiError(await detailOf(response), response.status);
  return response.json() as Promise<T>;
}

export function jsonBody(body: unknown, method = "POST"): RequestInit {
  return {
    method,
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  };
}

export function errorMessage(error: unknown): string {
  const value =
    typeof error === "object" && error !== null
      ? (error as { name?: unknown; message?: unknown })
      : null;
  if (value?.name === "AbortError")
    return "Consulta detenida. Revisa el historial antes de repetir una acción.";
  if (value?.name === "TimeoutError")
    return "El servidor tardó demasiado. Revisa el historial antes de repetir una acción; podría haberse completado.";
  if (value?.name === "TypeError" && value.message === "Failed to fetch")
    return "No hay conexión con el servidor. Comprueba que el backend esté en marcha.";
  return typeof value?.message === "string" && value.message
    ? value.message
    : "Error inesperado";
}

/** RFC 4122 v4 id for idempotent requests; falls back where randomUUID is missing. */
export function requestId(): string {
  if (typeof crypto.randomUUID === "function") return crypto.randomUUID();
  const bytes = new Uint8Array(16);
  crypto.getRandomValues(bytes);
  bytes[6] = (bytes[6] & 0x0f) | 0x40;
  bytes[8] = (bytes[8] & 0x3f) | 0x80;
  const hex = Array.from(bytes, (b) => b.toString(16).padStart(2, "0")).join("");
  return `${hex.slice(0, 8)}-${hex.slice(8, 12)}-${hex.slice(12, 16)}-${hex.slice(16, 20)}-${hex.slice(20)}`;
}
