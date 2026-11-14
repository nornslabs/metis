import { NextResponse } from "next/server";
import { auth } from "./lib/auth";

export const proxy=auth((req) => {
  // const isLoggedIn = !!req.auth;
  // const isApiRoute = req.nextUrl.pathname.startsWith("/api");

  // // Allow API routes (they handle their own auth)
  // if (isApiRoute) {
  //   return NextResponse.next();
  // }

  // // Redirect unauthenticated users to sign-in
  // if (!isLoggedIn) {
  //   const callbackUrl = encodeURIComponent(req.nextUrl.pathname + req.nextUrl.search);
  //   return NextResponse.redirect(new URL(`/auth/signin?callbackUrl=${callbackUrl}`, req.url));
  // }

  return NextResponse.next();
});

export const config={
  matcher: [
    /*
     * Match all request paths except for the ones starting with:
     * - _next/static (static files)
     * - _next/image (image optimization files)
     * - favicon.ico (favicon file)
     * - public folder
     * - api routes (handled by API)
     * - auth routes (signin, callback, error - publicly accessible)
     */
    "/((?!_next/static|_next/image|favicon.ico|public|api|auth).*)",
  ],
};