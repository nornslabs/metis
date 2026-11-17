import type { Metadata } from "next";
import { Suspense } from "react";

import { SignInCard } from "@/components/auth/sign-in-card";
import { SignInPitch } from "@/components/auth/sign-in-pitch";

export const metadata: Metadata = { title: "Sign in · Metis" };

export default function SignInPage({ searchParams }: PageProps<"/sign-in">) {
  return (
    <div className="mx-auto grid w-(--frame) flex-1 grid-cols-split max-stacked:grid-cols-1">
      <SignInPitch />
      <section className="flex items-center justify-center p-8 max-stacked:order-first max-stacked:border-b max-stacked:px-6 max-stacked:pt-7 max-stacked:pb-9 max-compact:px-4 max-compact:pt-6 max-compact:pb-8">
        <Suspense fallback={null}>
          <SignInCard searchParams={searchParams} />
        </Suspense>
      </section>
    </div>
  );
}
