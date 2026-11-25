"use client";

import { ExternalLink } from "lucide-react";
import Link from "next/link";
import { usePathname, useSearchParams } from "next/navigation";

import { PaneBanner } from "@/components/panel/pane-banner";
import { useStartExport } from "@/components/export/use-start-export";
import { Button, buttonVariants } from "@/components/ui/button";
import { useIdeaExport } from "@/lib/api/queries/use-export-summaries";
import { exportStatusView, progressLine, progressPercent, type ExportStatusView } from "@/lib/export/status";
import { useLiveExport } from "@/lib/export/live-export";
import { withSettingsTab } from "@/lib/settings/tab";

const LINK_CLASS = buttonVariants({ size: "sm" });

function Counts({ created, updated, links }: { created: number; updated: number; links: number }) {
  return (
    <p className="text-meta text-muted-foreground">{`${created} created · ${updated} updated · ${links} links`}</p>
  );
}

function ProjectLink({ url }: { url: string }) {
  return (
    <a href={url} target="_blank" rel="noopener noreferrer" className={LINK_CLASS}>
      Open in Linear
      <ExternalLink size={12} aria-hidden="true" />
    </a>
  );
}

function Running({ view }: { view: Extract<ExportStatusView, { kind: "running" }> }) {
  const progress = view.progress;
  const percent = progress ? progressPercent(progress) : 0;
  return (
    <section aria-label="Linear export" className="m-4 grid gap-1.5 border p-2.5 text-control">
      <div className="flex items-baseline justify-between gap-2">
        <b className="font-medium">Exporting to Linear…</b>
        {progress ? <span className="text-meta text-muted-foreground">{`${progress.done} / ${progress.total}`}</span> : null}
      </div>
      <div
        role="progressbar"
        aria-label="Export progress"
        aria-valuemin={0}
        aria-valuemax={100}
        aria-valuenow={percent}
        className="h-1.5 border"
      >
        <div className="h-full origin-left bg-foreground transition-transform duration-200" style={{ transform: `scaleX(${percent / 100})` }} />
      </div>
      {progress ? (
        <p role="status" className="truncate text-meta text-muted-foreground">
          {progressLine(progress)}
        </p>
      ) : null}
    </section>
  );
}

function Succeeded({ view }: { view: Extract<ExportStatusView, { kind: "succeeded" }> }) {
  return (
    <section aria-label="Linear export" className="m-4 grid gap-2 border p-2.5 text-control">
      <b className="font-medium text-success">Exported to Linear</b>
      <Counts created={view.created} updated={view.updated} links={view.links} />
      {view.projectUrl ? (
        <div>
          <ProjectLink url={view.projectUrl} />
        </div>
      ) : null}
    </section>
  );
}

function Failed({ ideaId, view }: { ideaId: string; view: Extract<ExportStatusView, { kind: "failed" }> }) {
  const exporter = useStartExport(ideaId);
  const pathname = usePathname();
  const search = useSearchParams();
  const settingsHref = withSettingsTab(pathname, new URLSearchParams(search), "integrations");
  return (
    <PaneBanner className="m-4 grid">
      <b className="font-medium">{view.reconnect ? "Linear needs to be reconnected." : "The export did not finish."}</b>
      <span className="text-meta">{view.message}</span>
      {view.created + view.updated + view.links > 0 ? <Counts created={view.created} updated={view.updated} links={view.links} /> : null}
      {view.failed.length > 0 ? (
        <ul className="grid gap-0.5 text-meta">
          {view.failed.map((item, index) => (
            <li key={`${index}:${item.kind}:${item.name}`} className="flex gap-1.5">
              <span className="text-muted-foreground">{item.kind}</span>
              <span className="min-w-0 flex-1 truncate">{item.name}</span>
              <span className="text-muted-foreground">{item.reason}</span>
            </li>
          ))}
        </ul>
      ) : null}
      {exporter.error ? <span className="text-meta text-destructive">{exporter.error}</span> : null}
      <div className="flex flex-wrap gap-1.5">
        {view.reconnect ? (
          <Link href={settingsHref} className={LINK_CLASS}>
            Reconnect Linear
          </Link>
        ) : (
          <Button type="button" size="sm" disabled={exporter.pending} onClick={exporter.start}>
            Retry export
          </Button>
        )}
        {view.projectUrl ? <ProjectLink url={view.projectUrl} /> : null}
      </div>
    </PaneBanner>
  );
}

/** The Plan pane's export block: progress while it runs, then the result (also after a reload). */
export function ExportStatus({ ideaId }: { ideaId: string }) {
  const live = useLiveExport(ideaId);
  const { summary } = useIdeaExport(ideaId);
  const view = exportStatusView(live, summary);
  if (view.kind === "idle") return null;
  if (view.kind === "running") return <Running view={view} />;
  if (view.kind === "succeeded") return <Succeeded view={view} />;
  return <Failed ideaId={ideaId} view={view} />;
}
