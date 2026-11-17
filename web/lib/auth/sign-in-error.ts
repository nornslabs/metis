export const GENERIC_SIGN_IN_ERROR = "Sign-in didn't finish. Try again.";

const MESSAGES: Readonly<Record<string, string>> = {
  "auth.oauth_state_invalid": "Your sign-in link expired. Try again.",
  "auth.oauth_failed": "Google sign-in failed. Try again.",
  "auth.email_unverified": "Your Google email is not verified.",
};

/** Maps the `?error=<code>` the server puts on `/sign-in` to a message, or null for none. */
export function signInErrorMessage(code: string | undefined): string | null {
  if (!code) return null;
  return MESSAGES[code] ?? GENERIC_SIGN_IN_ERROR;
}
