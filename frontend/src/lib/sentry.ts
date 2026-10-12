/**
 * What error reports may carry: no user info, cookies or request bodies, and no reset
 * token from a URL (shared by the server and browser Sentry setups).
 */
import type { BrowserOptions } from "@sentry/nextjs";

export const dataCollection: BrowserOptions["dataCollection"] = {
  userInfo: false,
  cookies: false,
  httpBodies: [],
  httpHeaders: { request: { deny: ["cookie", "authorization"] }, response: false },
  urlQueryParams: { deny: ["token"] },
};
