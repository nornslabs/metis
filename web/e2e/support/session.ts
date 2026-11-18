import { execFileSync } from "node:child_process";
import { createHash, randomUUID } from "node:crypto";

export const SESSION_COOKIE = process.env.E2E_SESSION_COOKIE ?? "metis_session";
export const USER_EMAIL = "e2e-ship221@example.com";

const USER_ID = "00000000-0000-7000-8000-000000000221";

/** Runs SQL as the superuser in the compose Postgres (test setup only). */
export function psql(sql: string): void {
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

const OWNER_ID = "00000000-0000-7000-8000-000000000224";
const MEMBER_WORKSPACE_ID = "00000000-0000-7000-8000-000000000225";

/**
 * A workspace owned by another user where the test user is only a member. Returns its id, to be
 * sent as `X-Workspace-Id` (or set in the workspace cookie).
 */
export function seedMemberWorkspace(): string {
  psql(`
    insert into auth.users (id, email, name) values ('${OWNER_ID}', 'e2e-owner-ship224@example.com', 'E2E Owner')
      on conflict do nothing;
    insert into identity.workspaces (id, name, created_by, is_personal)
      values ('${MEMBER_WORKSPACE_ID}', 'Owner team', '${OWNER_ID}', false) on conflict do nothing;
    insert into identity.members (workspace_id, user_id, role) values
      ('${MEMBER_WORKSPACE_ID}', '${OWNER_ID}', 'owner'),
      ('${MEMBER_WORKSPACE_ID}', '${USER_ID}', 'member') on conflict do nothing;
  `);
  return MEMBER_WORKSPACE_ID;
}

/** Workspaces do not cascade from users, so they go first; the rest cascades from the users. */
export function removeUser(): void {
  const ids = `'${USER_ID}', '${OWNER_ID}'`;
  psql(`
    delete from identity.workspaces where created_by in (${ids});
    delete from auth.users where id in (${ids});
  `);
}
