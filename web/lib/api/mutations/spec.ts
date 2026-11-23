import { apiClient } from "@/lib/api/client";
import { bodyOf } from "@/lib/api/result";
import {
  specConfirmedSchema,
  specOverviewSchema,
  specVersionSchema,
  type SpecConfirmed,
  type SpecOverview,
  type SpecVersion,
} from "@/lib/schemas/spec";

/** Saves `contentMd` as a new version on top of `baseNumber` (`POST /v1/ideas/{id}/spec/versions`). 409 `spec.conflict` when it is no longer the newest. */
export async function saveSpecVersion(ideaId: string, baseNumber: number, contentMd: string): Promise<SpecVersion> {
  const result = await apiClient.POST("/v1/ideas/{idea_id}/spec/versions", {
    params: { path: { idea_id: ideaId } },
    body: { base_number: baseNumber, content_md: contentMd },
  });
  return specVersionSchema.parse(bodyOf(result));
}

/** Confirms version `number` and resumes the run waiting on it (`POST /v1/ideas/{id}/spec/confirm`). */
export async function confirmSpecVersion(ideaId: string, number: number): Promise<SpecConfirmed> {
  const result = await apiClient.POST("/v1/ideas/{idea_id}/spec/confirm", {
    params: { path: { idea_id: ideaId } },
    body: { number },
  });
  return specConfirmedSchema.parse(bodyOf(result));
}

/** Reads the latest and confirmed versions (`GET /v1/ideas/{id}/spec`). */
export async function fetchSpecOverview(ideaId: string): Promise<SpecOverview> {
  const result = await apiClient.GET("/v1/ideas/{idea_id}/spec", { params: { path: { idea_id: ideaId } } });
  return specOverviewSchema.parse(bodyOf(result));
}
