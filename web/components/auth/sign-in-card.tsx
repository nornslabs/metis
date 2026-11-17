import { Lock } from "lucide-react";
import Link from "next/link";
import { redirect } from "next/navigation";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { getMe } from "@/lib/auth/get-me";
import { getProviders } from "@/lib/auth/get-providers";
import { safeRedirectPath } from "@/lib/auth/redirect";
import { firstParam } from "@/lib/search-params";
import { signInErrorMessage } from "@/lib/auth/sign-in-error";

import { GoogleButton } from "./google-button";

const UNREACHABLE_MESSAGE = "Can't reach Metis right now. Try again in a moment.";

type SearchParams = Promise<Record<string, string | string[] | undefined>>;

export async function SignInCard({ searchParams }: { searchParams: SearchParams }) {
  const params = await searchParams;
  const redirectTo = safeRedirectPath(params.redirect_to);

  if (await getMe()) redirect(redirectTo);

  const providers = await getProviders();
  const errorMessage =
    signInErrorMessage(firstParam(params.error)) ??
    (providers === null ? UNREACHABLE_MESSAGE : null);

  return (
    <div className="grid w-full max-w-card gap-3.5">
      <div>
        <h2 className="text-title font-semibold tracking-tight">Sign in to Metis</h2>
        <p className="mt-0.5 text-control text-muted-foreground">
          New here? Signing in creates your workspace.
        </p>
      </div>

      {errorMessage ? (
        <div
          role="alert"
          className="border border-destructive/40 px-2.5 py-2 text-xs text-destructive"
        >
          {errorMessage}
        </div>
      ) : null}

      {providers?.includes("google") ? <GoogleButton redirectTo={redirectTo} /> : null}

      <div className="flex items-center gap-3 text-micro uppercase tracking-divider text-muted-foreground before:h-px before:flex-1 before:bg-border after:h-px after:flex-1 after:bg-border">
        or
      </div>

      <div className="grid gap-1">
        <Label htmlFor="email" className="flex items-center justify-between text-xs">
          Email
          <Badge
            variant="outline"
            className="h-auto px-1.5 py-px text-micro font-medium uppercase tracking-label text-muted-foreground"
          >
            Soon
          </Badge>
        </Label>
        <Input
          id="email"
          type="email"
          placeholder="you@company.com"
          disabled
          className="h-control text-control disabled:bg-transparent disabled:opacity-100"
        />
      </div>
      <Button variant="outline" size="lg" disabled className="h-8 w-full text-control">
        Email me a sign-in link
      </Button>

      <div className="flex gap-2 border px-2.5 py-2 text-note text-muted-foreground">
        <Lock size={14} strokeWidth={2} className="mt-0.5 shrink-0" aria-hidden="true" />
        <span>
          Bring your own LLM and Exa keys after sign-in. They&apos;re encrypted and never shown
          again.
        </span>
      </div>

      <p className="text-meta text-muted-foreground">
        By continuing you agree to the{" "}
        <Link href="/terms" className="text-foreground underline underline-offset-3">
          Terms
        </Link>{" "}
        and{" "}
        <Link href="/privacy" className="text-foreground underline underline-offset-3">
          Privacy Policy
        </Link>
        .
      </p>
    </div>
  );
}
