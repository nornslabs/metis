import type { NextConfig } from "next";

// Read at build time (the standalone output bakes rewrites into the routes manifest).
const API_ORIGIN = process.env.API_ORIGIN ?? "http://localhost:8000";

const nextConfig: NextConfig = {
  output: "standalone",
  // Off: gzip buffers the proxied `/v1/runs/{id}/events` stream, so no event reaches the page
  // until the run ends. The API and any front proxy handle compression for the rest.
  compress: false,
  cacheComponents: true,
  partialPrefetching: true,
  turbopack: {
    // The generated components/ui files import `cn` straight from the package; point them at the
    // merger that knows our custom lengths (lib/cn.ts).
    resolveAlias: { cn: "./lib/cn.ts" },
    rules: {
      "*.css": {
        loaders: ["@tailwindcss/turbopack"],
        as: "*.css",
      },
    },
  },
  // Same-origin API: the session cookie is first-party and no CORS is needed.
  async rewrites() {
    return [{ source: "/v1/:path*", destination: `${API_ORIGIN}/v1/:path*` }];
  },
};

export default nextConfig;
