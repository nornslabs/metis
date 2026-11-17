/** The current step while nothing has streamed (ui-context.md, Shimmer). Static under reduced motion. */
export function Shimmer({ children }: { children: string }) {
  return <div className="w-max text-control font-medium text-shimmer">{children}</div>;
}
