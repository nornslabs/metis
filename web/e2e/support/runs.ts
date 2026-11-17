import { randomUUID } from "node:crypto";

import { psql } from "./session";

/**
 * Inserts a `queued` run with no job behind it, so it stays queued until the test acts. Returns
 * its id. Ids are UUIDs generated here; the values are not user input.
 */
export function seedQueuedRun(ideaId: string, workspaceId: string): string {
  const runId = randomUUID();
  psql(`
    insert into ideas.workflow_runs (id, workspace_id, idea_id, status)
      values ('${runId}', '${workspaceId}', '${ideaId}', 'queued');
  `);
  return runId;
}

type FakeEvent = { type: string; data: unknown; id?: string };

/** A `text/event-stream` body in the server's frame format (`retry`, `id`, `event`, `data`). */
export function eventStreamBody(runId: string, events: readonly (FakeEvent | string)[]): string {
  const frames = events.map((event, index) => {
    if (typeof event === "string") return event;
    const envelope = { run_id: runId, type: event.type, data: event.data, ts: new Date().toISOString() };
    return `id: ${event.id ?? `1-${index}`}\nevent: ${event.type}\ndata: ${JSON.stringify(envelope)}\n\n`;
  });
  return ["retry: 3000\n\n", ...frames].join("");
}
