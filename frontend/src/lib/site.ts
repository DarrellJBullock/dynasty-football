/**
 * Where a view's links go: the game (the default), or a league's read-only public link
 * (`/share/{token}`), where there are no player pages, nothing to coach and nothing to sim.
 */
export interface Site {
  /** Prefix for the view's links ("" in the game). */
  base: string;
  /** A read-only public view. */
  shared: boolean;
}

export const GAME: Site = { base: "", shared: false };

export function sharedSite(token: string): Site {
  return { base: `/share/${encodeURIComponent(token)}`, shared: true };
}
