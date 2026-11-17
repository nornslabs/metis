import Link from "next/link";
import type { ReactNode } from "react";

import { SIGN_IN_PATH } from "@/lib/auth/redirect";

type LegalPageProps = {
  title: string;
  updated: string;
  children: ReactNode;
};

/** A readable document page inside the public frame (terms, privacy). */
export function LegalPage({ title, updated, children }: LegalPageProps) {
  return (
    <article className="mx-auto w-(--frame) flex-1 px-4 py-10 max-compact:py-6">
      <div className="grid max-w-prose gap-5">
        <Link
          href={SIGN_IN_PATH}
          className="text-meta text-muted-foreground underline-offset-3 hover:text-foreground hover:underline"
        >
          ← Back to sign in
        </Link>
        <header className="grid gap-1">
          <h1 className="text-xl font-semibold tracking-tight">{title}</h1>
          <p className="text-meta text-muted-foreground">Last updated {updated}</p>
        </header>
        {children}
      </div>
    </article>
  );
}

export function LegalSection({ heading, children }: { heading: string; children: ReactNode }) {
  return (
    <section className="grid gap-1.5">
      <h2 className="text-body font-semibold">{heading}</h2>
      <div className="grid gap-2 text-muted-foreground">{children}</div>
    </section>
  );
}

export function LegalLink({ href, children }: { href: string; children: ReactNode }) {
  return (
    <Link href={href} className="text-foreground underline underline-offset-3">
      {children}
    </Link>
  );
}
