import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  // End-to-end tests build into their own folder so they never clash with `next dev`.
  distDir: process.env.NEXT_DIST_DIR || ".next",
  // The Docker image runs Next.js's self-contained server (frontend/Dockerfile).
  output: process.env.NEXT_OUTPUT === "standalone" ? "standalone" : undefined,
  cacheComponents: true,
  // (The browser's /api/* goes on to the game server through src/proxy.ts, at request
  // time, so the API's address isn't baked into the build.)
  partialPrefetching: true,
  turbopack: {
    rules: {
      "*.css": {
        loaders: ["@tailwindcss/turbopack"],
        as: "*.css",
      },
    },
  },
};

export default nextConfig;
