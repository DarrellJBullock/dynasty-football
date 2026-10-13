import { NextResponse, type NextRequest } from "next/server";
import { gameServerUrl } from "@/lib/gameServer";

/** The session cookie the game server sets (backend app/api/access.py). */
export const SESSION_COOKIE = "df_session";

/** Pages that don't need a session. */
const PUBLIC = ["/signin", "/signup", "/forgot-password", "/reset-password"];
/** ...and every page under these (a league's read-only public link). */
const PUBLIC_PREFIXES = ["/share/"];

/**
 * Runs before every request (but Next.js's own files):
 *
 * - `/api/*` goes on to the game server (`gameServerUrl`), read at request time so one build
 *   (one Docker image) serves any environment. The browser's cookies go along; each
 *   request gets an `X-Request-ID` the API logs and returns.
 * - Other pages need a session cookie, or go to sign in and back afterwards. Only a quick
 *   check that the cookie is there: the game server decides whether it's valid (and pages
 *   it turns away also go to sign in, via `attempt`).
 */
export function proxy(request: NextRequest) {
  const { pathname, search } = request.nextUrl;
  if (pathname.startsWith("/api/")) {
    const target = new URL(pathname + search, gameServerUrl());
    const headers = new Headers(request.headers);
    if (!headers.has("x-request-id")) headers.set("x-request-id", crypto.randomUUID());
    return NextResponse.rewrite(target, { request: { headers } });
  }
  if (PUBLIC.includes(pathname) || PUBLIC_PREFIXES.some((p) => pathname.startsWith(p))
    || request.cookies.has(SESSION_COOKIE)) return NextResponse.next();
  const signIn = new URL("/signin", request.url);
  const next = pathname + search;
  if (next !== "/") signIn.searchParams.set("next", next);
  return NextResponse.redirect(signIn);
}

export const config = {
  matcher: ["/((?!_next/|favicon.ico).*)"],
};
