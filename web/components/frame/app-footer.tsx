export function AppFooter() {
  return (
    <footer data-frame="footer" className="relative z-10 min-h-(--footer-h) shrink-0 border-t">
      <div className="mx-auto flex w-(--frame) items-center justify-center px-4 py-1.5 text-center text-meta text-muted-foreground">
        Metis uses your own LLM and Exa keys. Scores are estimates, not advice.
      </div>
    </footer>
  );
}
