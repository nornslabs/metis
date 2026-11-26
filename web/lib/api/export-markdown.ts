import { apiClient } from "@/lib/api/client";
import { bodyOf } from "@/lib/api/result";
import { downloadTextFile } from "@/lib/download";

const FALLBACK_FILE_NAME = "metis-plan.md";
const FILE_NAME_PATTERN = /filename="([^"\\/]+)"/;

/** The file name in a `Content-Disposition` header, or a safe default. */
export function fileNameFrom(disposition: string | null): string {
  const match = disposition ? FILE_NAME_PATTERN.exec(disposition) : null;
  return match?.[1] ?? FALLBACK_FILE_NAME;
}

/** Downloads the idea's confirmed spec, score and plan as one Markdown file (`GET /v1/ideas/{id}/export.md`). */
export async function downloadPlanMarkdown(ideaId: string): Promise<void> {
  const result = await apiClient.GET("/v1/ideas/{idea_id}/export.md", {
    params: { path: { idea_id: ideaId } },
    parseAs: "text",
  });
  const text = bodyOf(result as { data?: string });
  downloadTextFile(fileNameFrom(result.response.headers.get("Content-Disposition")), text);
}
