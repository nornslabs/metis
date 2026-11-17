import { describe, expect, it, vi } from "vitest";

import { createApiClient } from "./create-client";
import { ApiError } from "./errors";

type Recorded = { url: string; method: string; headers: Headers; credentials: string };

function problem(status: number, code: string, extra: Record<string, unknown> = {}): Response {
  return new Response(
    JSON.stringify({
      title: "Title",
      status,
      code,
      detail: "Detail",
      request_id: "req-1",
      retryable: false,
      ...extra,
    }),
    { status, headers: { "Content-Type": "application/problem+json" } },
  );
}

function setup(
  respond: (request: Request) => Response = () => Response.json({ ok: true }),
  options: { workspaceId?: string | null; onWorkspaceRejected?: () => void } = {},
) {
  const calls: Recorded[] = [];
  const fetchFake = vi.fn(async (input: Request) => {
    calls.push({
      url: input.url,
      method: input.method,
      headers: input.headers,
      credentials: input.credentials,
    });
    return respond(input);
  });
  const client = createApiClient({
    baseUrl: "http://web.test",
    fetch: fetchFake as unknown as typeof fetch,
    credentials: "include",
    getWorkspaceId: () => options.workspaceId ?? null,
    onWorkspaceRejected: options.onWorkspaceRejected,
  });
  return { client, calls };
}

describe("createApiClient headers", () => {
  it.each(["POST", "PUT", "PATCH", "DELETE"] as const)("sends X-Metis-Client on %s", async (m) => {
    const { client, calls } = setup();
    await client.request(m.toLowerCase() as "post", "/v1/auth/logout" as never, {} as never);
    expect(calls[0].headers.get("X-Metis-Client")).toBe("web");
  });

  it("does not send X-Metis-Client on GET", async () => {
    const { client, calls } = setup();
    await client.GET("/v1/auth/me");
    expect(calls[0].headers.get("X-Metis-Client")).toBeNull();
  });

  it("never sends Authorization", async () => {
    const { client, calls } = setup(undefined, { workspaceId: "ws-1" });
    await client.GET("/v1/auth/me");
    await client.request("post", "/v1/auth/logout" as never, {} as never);
    expect(calls.every((c) => !c.headers.has("Authorization"))).toBe(true);
  });

  it("sends X-Workspace-Id when a workspace is chosen", async () => {
    const { client, calls } = setup(undefined, { workspaceId: "ws-1" });
    await client.GET("/v1/auth/me");
    expect(calls[0].headers.get("X-Workspace-Id")).toBe("ws-1");
  });

  it("omits X-Workspace-Id when none is chosen", async () => {
    const { client, calls } = setup();
    await client.GET("/v1/auth/me");
    expect(calls[0].headers.has("X-Workspace-Id")).toBe(false);
  });

  it("includes credentials", async () => {
    const { client, calls } = setup();
    await client.GET("/v1/auth/me");
    expect(calls[0].credentials).toBe("include");
  });
});

describe("createApiClient errors", () => {
  it("throws ApiError with code, status and request_id on a 409", async () => {
    const { client } = setup(() => problem(409, "run.already_running"));
    const error = await client.GET("/v1/auth/me").catch((e: unknown) => e);
    expect(error).toBeInstanceOf(ApiError);
    expect(error).toMatchObject({ status: 409, code: "run.already_running", request_id: "req-1" });
  });

  it("turns a non-JSON 500 into common.unexpected", async () => {
    const { client } = setup(() => new Response("<html>boom</html>", { status: 500 }));
    const error = await client.GET("/v1/auth/me").catch((e: unknown) => e);
    expect(error).toMatchObject({ status: 500, code: "common.unexpected" });
  });

  it("returns data on success", async () => {
    const { client } = setup(() => Response.json({ id: "u1" }));
    const result = await client.GET("/v1/auth/me");
    expect(result.data).toEqual({ id: "u1" });
  });

  it("clears the workspace when 403 auth.forbidden answers a call that sent it", async () => {
    const onWorkspaceRejected = vi.fn();
    const { client } = setup(() => problem(403, "auth.forbidden"), {
      workspaceId: "ws-1",
      onWorkspaceRejected,
    });
    await client.GET("/v1/auth/me").catch(() => undefined);
    expect(onWorkspaceRejected).toHaveBeenCalledTimes(1);
  });

  it("keeps the workspace on 403 auth.forbidden when none was sent", async () => {
    const onWorkspaceRejected = vi.fn();
    const { client } = setup(() => problem(403, "auth.forbidden"), { onWorkspaceRejected });
    await client.GET("/v1/auth/me").catch(() => undefined);
    expect(onWorkspaceRejected).not.toHaveBeenCalled();
  });

  it("keeps the workspace on other 403 codes", async () => {
    const onWorkspaceRejected = vi.fn();
    const { client } = setup(() => problem(403, "auth.csrf_failed"), {
      workspaceId: "ws-1",
      onWorkspaceRejected,
    });
    await client.GET("/v1/auth/me").catch(() => undefined);
    expect(onWorkspaceRejected).not.toHaveBeenCalled();
  });
});
