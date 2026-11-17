import { ApiError, errorMessage, upstreamReason } from "@/lib/api/errors";

const UPSTREAM_CODE = "provider.upstream_error";

const REASON_MESSAGES: Readonly<Record<string, string>> = {
  unauthorized: "The provider rejected the key.",
  unreachable: "Couldn't reach the provider. Check the base URL.",
  timeout: "The provider took too long to answer.",
  rate_limited: "The provider is rate limiting this key.",
  server_error: "The provider had an error. Try again.",
  bad_response: "The provider sent an answer Metis can't read.",
};

/** What to show next to a key whose test failed: the upstream reason in words, else the API message. */
export function testFailureMessage(error: unknown): string {
  if (!(error instanceof ApiError)) return "Couldn't test the key. Try again.";
  if (error.code === UPSTREAM_CODE) {
    const reason = upstreamReason(error);
    if (reason && REASON_MESSAGES[reason]) return REASON_MESSAGES[reason];
  }
  return errorMessage(error);
}
