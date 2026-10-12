import { NextResponse, type NextRequest } from "next/server";

/** The session cookie the game server sets (backend app/api/access.py). */
export const SESSION_COOKIE = "df_session";

/**
 * Visitors without a session go to sign in, then back where they were headed. Only a
 * quick check that the cookie is there: the game server decides whether it's valid (and
 * pages it turns away also go to sign in, via `attempt`).
 */
export function proxy(request: NextRequest) {
  if (request.cookies.has(SESSION_COOKIE)) return NextResponse.next();
  const signIn = new URL("/signin", request.url);
  const next = request.nextUrl.pathname + request.nextUrl.search;
  if (next !== "/") signIn.searchParams.set("next", next);
  return NextResponse.redirect(signIn);
}

export const config = {
  // Every page but signing in and up; not the API proxy or Next.js's own files.
  matcher: ["/((?!api/|_next/|favicon.ico|signin|signup).*)"],
};
