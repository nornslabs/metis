import { psql, USER_ID } from "./session";

/**
 * Saves an LLM key row that has passed its test in the test user's personal workspace, so the
 * server's start gate lets stub runs begin. The sealed secret is empty: stub specialists never
 * decrypt it, and the gate reads only the row. Call after the workspace exists (any API call).
 */
export function seedTestedLlmKey(): void {
  psql(`
    insert into identity.provider_keys (id, workspace_id, kind, sealed, masked, last_tested_at, last_test_ok)
    select gen_random_uuid(), w.id, 'llm', '{}'::jsonb, 'sk-…e2e0', now(), true
    from identity.workspaces w where w.created_by = '${USER_ID}' and w.is_personal
    on conflict (workspace_id, kind) do update set last_test_ok = true, last_tested_at = now();
  `);
}

export function removeSeededLlmKey(): void {
  psql(`
    delete from identity.provider_keys
    where kind = 'llm' and sealed = '{}'::jsonb
      and workspace_id in (select id from identity.workspaces where created_by = '${USER_ID}' and is_personal);
  `);
}
