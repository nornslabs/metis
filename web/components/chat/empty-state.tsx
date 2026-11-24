import { RecentIdeas } from "@/components/chat/recent-ideas";
import { OWL_FACE_PATH } from "@/lib/brand/owl-path";

/** The faint outlined owl above the title; hidden on a short window to leave room for the rest. */
function HeroOwl() {
  return (
    <svg data-testid="hero-owl" viewBox="0 0 24 24" aria-hidden="true" focusable="false" className="mb-1.5 size-19 text-muted-foreground opacity-55 short:hidden">
      <path d={OWL_FACE_PATH} fill="none" stroke="currentColor" strokeWidth={0.35} strokeLinejoin="miter" fillRule="evenodd" />
      <g fill="currentColor" opacity={0.8}>
        <circle cx="8.5" cy="11" r="1.3" />
        <circle cx="15.5" cy="11" r="1.3" />
      </g>
    </svg>
  );
}

/** The empty chat's hero on `/`: owl, "What are you building?", one line, and the recent ideas. */
export function EmptyState() {
  return (
    <section className="flex flex-1 flex-col items-center justify-center gap-1.5 px-5 py-8 text-center">
      <HeroOwl />
      <h1 className="text-2xl font-semibold tracking-tight">What are you building?</h1>
      <p className="max-w-lead text-body text-muted-foreground">
        Describe your idea in a sentence or two. Metis will ask a few questions, research the market and
        score it.
      </p>
      <RecentIdeas />
    </section>
  );
}
