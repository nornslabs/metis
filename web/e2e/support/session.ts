import { execFileSync } from "node:child_process";
import { createHash, randomUUID } from "node:crypto";

export const SESSION_COOKIE = process.env.E2E_SESSION_COOKIE ?? "metis_session";
export const USER_EMAIL = "e2e-ship221@example.com";

const USER_ID = "00000000-0000-7000-8000-000000000221";

function psql(sql: string): void {
  execFileSync(
    "docker",
    ["compose", "exec", "-T", "postgres", "psql", "-U", "postgres", "-d", "metis", "-q", "-c", sql],
    { cwd: "..", stdio: "pipe" },
  );
}

export function seedUser(): void {
  psql(`
    insert into auth.users (id, email, name) values ('${USER_ID}', '${USER_EMAIL}', 'E2E Tester')
      on conflict do nothing;
  `);
}

/**
 * Inserts a live session for the test user and returns its token. A fresh token per call: a
 * sign-out leaves a Redis tombstone on the old token's hash.
 */
export function createSessionToken(): string {
  const token = `e2e-${randomUUID()}`;
  const hash = createHash("sha256").update(token).digest("hex");
  psql(`
    insert into auth.sessions (id, user_id, token_hash, expires_at)
      values ('${randomUUID()}', '${USER_ID}', decode('${hash}', 'hex'), now() + interval '1 day');
  `);
  return token;
}

/** Deleting the user cascades to its sessions and identities. */
export function removeUser(): void {
  psql(`delete from auth.users where id = '${USER_ID}';`);
}
