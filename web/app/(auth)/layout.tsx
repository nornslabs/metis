import type { ReactNode } from "react";

import { AuthFooter } from "@/components/auth/auth-footer";
import { AuthHeader } from "@/components/auth/auth-header";
import { FrameBackground } from "@/components/frame/frame-background";

export default function AuthLayout({ children }: { children: ReactNode }) {
  return (
    <div className="relative flex min-h-svh flex-col">
      <FrameBackground />
      <AuthHeader />
      <main className="relative z-10 flex flex-1 flex-col">{children}</main>
      <AuthFooter />
    </div>
  );
}
