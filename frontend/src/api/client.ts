import type {
  CompileRequest,
  CompileResult,
  ExampleProgram,
  HealthInfo,
  LanguageInfo,
} from './schema';

const API_BASE_URL = import.meta.env.VITE_API_BASE_URL || '';

export class ApiRequestError extends Error {
  code: string;
  status: number;
  retryAfter?: number;
  requestId?: string;

  constructor(
    message: string,
    status: number,
    code: string,
    retryAfter?: number,
    requestId?: string
  ) {
    super(message);
    this.name = 'ApiRequestError';
    this.status = status;
    this.code = code;
    this.retryAfter = retryAfter;
    this.requestId = requestId;
  }
}

/**
 * Fetch health status of the Nexora API.
 */
export async function getHealth(signal?: AbortSignal): Promise<HealthInfo> {
  const res = await fetch(`${API_BASE_URL}/api/v1/health`, { signal });
  if (!res.ok) {
    throw new ApiRequestError('Failed to check health', res.status, 'health_error');
  }
  return res.json();
}

/**
 * Fetch MiniLang language specification metadata for Monarch syntax highlighting.
 */
export async function getLanguage(signal?: AbortSignal): Promise<LanguageInfo> {
  const res = await fetch(`${API_BASE_URL}/api/v1/language`, { signal });
  if (!res.ok) {
    throw new ApiRequestError('Failed to fetch language metadata', res.status, 'language_error');
  }
  return res.json();
}

/**
 * Fetch bundled sample programs.
 */
export async function getExamples(signal?: AbortSignal): Promise<ExampleProgram[]> {
  const res = await fetch(`${API_BASE_URL}/api/v1/examples`, { signal });
  if (!res.ok) {
    throw new ApiRequestError('Failed to fetch examples', res.status, 'examples_error');
  }
  return res.json();
}

/**
 * Compile MiniLang source code and optionally run in sandbox.
 */
export async function compile(
  req: CompileRequest,
  signal?: AbortSignal
): Promise<CompileResult> {
  let res: Response;
  try {
    res = await fetch(`${API_BASE_URL}/api/v1/compile`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
      },
      body: JSON.stringify(req),
      signal,
    });
  } catch (err: any) {
    if (err.name === 'AbortError') {
      throw err;
    }
    throw new ApiRequestError(
      'Cannot reach the Nexora server. Is the backend running on port 8000?',
      0,
      'network_error'
    );
  }

  const requestId = res.headers.get('X-Request-ID') || undefined;

  if (res.status === 413) {
    throw new ApiRequestError(
      'MiniLang program is larger than the 64 KB limit.',
      413,
      'source_too_large',
      undefined,
      requestId
    );
  }

  if (res.status === 429) {
    const retryHeader = res.headers.get('Retry-After');
    const retryAfter = retryHeader ? parseInt(retryHeader, 10) : 5;
    throw new ApiRequestError(
      `Too many requests — please wait ${retryAfter}s before retrying.`,
      429,
      'rate_limited',
      retryAfter,
      requestId
    );
  }

  if (res.status === 503) {
    throw new ApiRequestError(
      'Server is busy running other programs. Please retry in a few seconds.',
      503,
      'busy',
      undefined,
      requestId
    );
  }

  if (res.status === 500) {
    throw new ApiRequestError(
      `Internal compiler error occurred on server.${requestId ? ` (Request ID: ${requestId})` : ''}`,
      500,
      'internal_error',
      undefined,
      requestId
    );
  }

  if (!res.ok) {
    let message = 'Compilation request failed';
    let code = 'request_failed';
    try {
      const errBody = await res.json();
      if (errBody?.error?.message) {
        message = errBody.error.message;
        code = errBody.error.code || code;
      }
    } catch {
      // Ignore JSON parse errors for non-ok
    }
    throw new ApiRequestError(message, res.status, code, undefined, requestId);
  }

  return res.json();
}
