import { z } from "zod";

export const UNEXPECTED_CODE = "common.unexpected";
export const SESSION_ERROR_CODES: readonly string[] = [
  "auth.not_signed_in",
  "auth.session_expired",
];

const fieldErrorSchema = z.object({ field: z.string(), message: z.string() });

/** The problem+json body (shape in `server-context.md`). `status` comes from the HTTP response. */
const problemSchema = z.object({
  title: z.string(),
  code: z.string(),
  detail: z.string().nullish(),
  request_id: z.string().nullish(),
  retryable: z.boolean().default(false),
  errors: z.array(fieldErrorSchema).default([]),
  meta: z.record(z.string(), z.unknown()).nullish(),
});

export type FieldError = z.infer<typeof fieldErrorSchema>;

type ApiErrorInit = {
  status: number;
  code: string;
  title: string;
  detail?: string | null;
  request_id?: string | null;
  retryable?: boolean;
  errors?: readonly FieldError[];
  meta?: Readonly<Record<string, unknown>> | null;
};

/** Every non-2xx answer from the API. Branch on `code`, never on message text. */
export class ApiError extends Error {
  readonly status: number;
  readonly code: string;
  readonly title: string;
  readonly detail: string | null;
  readonly request_id: string | null;
  readonly retryable: boolean;
  readonly errors: readonly FieldError[];
  readonly meta: Readonly<Record<string, unknown>>;

  constructor(init: ApiErrorInit) {
    super(init.detail ?? init.title);
    this.name = "ApiError";
    this.status = init.status;
    this.code = init.code;
    this.title = init.title;
    this.detail = init.detail ?? null;
    this.request_id = init.request_id ?? null;
    this.retryable = init.retryable ?? false;
    this.errors = init.errors ?? [];
    this.meta = init.meta ?? {};
  }
}

/** Reads a non-2xx response into an `ApiError`; a body that is not problem+json is `common.unexpected`. */
export async function parseApiError(response: Response): Promise<ApiError> {
  const status = response.status;
  try {
    const problem = problemSchema.parse(await response.json());
    return new ApiError({ ...problem, status });
  } catch {
    return new ApiError({
      status,
      code: UNEXPECTED_CODE,
      title: "Something went wrong",
      detail: "The server sent an unexpected response.",
      retryable: status >= 500,
    });
  }
}

/** True for `auth.not_signed_in` and `auth.session_expired`: the session is gone. */
export function isSessionError(error: unknown): error is ApiError {
  return error instanceof ApiError && SESSION_ERROR_CODES.includes(error.code);
}

/** Narrows an unknown thrown value to `ApiError`. */
export function isApiError(error: unknown): error is ApiError {
  return error instanceof ApiError;
}

/** `meta.reason` of a `provider.upstream_error` (`unauthorized`, `unreachable`, `timeout`, …), if any. */
export function upstreamReason(error: ApiError): string | null {
  const reason = error.meta.reason;
  return typeof reason === "string" ? reason : null;
}

/** The message to show: `detail`, else `title`. */
export function errorMessage(error: ApiError): string {
  return error.detail ?? error.title;
}

export const NETWORK_ERROR_MESSAGE = "Could not reach Metis. Check your connection and try again.";

/** A message for any thrown value: the problem's text for an `ApiError`, else a generic line. */
export function describeError(error: unknown): string {
  return error instanceof ApiError ? errorMessage(error) : NETWORK_ERROR_MESSAGE;
}

// FastAPI locations start with where the value came from (`body.email`); forms name just the field.
const LOCATION_PREFIX = /^(body|query|path|header|cookie)\./;

/** `errors[]` as arguments for react-hook-form's `setError`: `fieldErrors(e).forEach(({name, error}) => setError(name, error))`. */
export function fieldErrors(
  error: ApiError,
): { name: string; error: { type: "server"; message: string } }[] {
  return error.errors.map(({ field, message }) => ({
    name: field.replace(LOCATION_PREFIX, ""),
    error: { type: "server", message },
  }));
}
