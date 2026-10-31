const BASE = '/api/v1';

/** Контракт ошибок — RFC 7807 (Design §12.1): code/detail/status. */
export interface ProblemDetails {
  type?: string;
  title?: string;
  status?: number;
  code?: string;
  detail?: string;
}

export class ApiError extends Error {
  readonly status: number;
  readonly code: string;

  constructor(status: number, code: string, message: string) {
    super(message);
    this.name = 'ApiError';
    this.status = status;
    this.code = code;
  }
}

/**
 * Общий REST-запрос к API v1. JSON — camelCase (Design §12.1),
 * cookies включаем (refresh — HttpOnly cookie, S-02).
 */
export async function apiFetch<T>(path: string, init: RequestInit = {}): Promise<T> {
  let response: Response;
  try {
    response = await fetch(`${BASE}${path}`, {
      ...init,
      credentials: 'include',
      headers: {
        'Content-Type': 'application/json',
        ...(init.headers ?? {}),
      },
    });
  } catch {
    throw new ApiError(0, 'network_error', 'Сеть недоступна: API не отвечает');
  }

  if (!response.ok) {
    const problem = (await response.json().catch(() => null)) as ProblemDetails | null;
    throw new ApiError(
      response.status,
      problem?.code ?? 'unknown_error',
      problem?.detail ?? problem?.title ?? `HTTP ${response.status}`,
    );
  }
  if (response.status === 204) {
    return undefined as T;
  }
  return (await response.json()) as T;
}

// --- DTO (заморозка контрактов — docs/SPEC.md)

export interface HealthDto {
  status: string;
  db: boolean;
  redis: boolean;
}

export const fetchHealth = (): Promise<HealthDto> => apiFetch<HealthDto>('/healthz');
