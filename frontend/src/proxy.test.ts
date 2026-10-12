// @vitest-environment node
import { NextRequest } from "next/server";
import { afterEach, describe, expect, it, vi } from "vitest";
import { proxy, SESSION_COOKIE } from "./proxy";

const request = (path: string, cookie?: string) =>
  new NextRequest(`http://localhost:3000${path}`, {
    headers: cookie ? { cookie: `${SESSION_COOKIE}=${cookie}` } : {},
  });

afterEach(() => vi.unstubAllEnvs());

describe("proxy", () => {
  it("sends /api on to the game server at API_URL, read at request time", () => {
    vi.stubEnv("API_URL", "http://api.internal:8000");
    const response = proxy(request("/api/teams/4/roster?sort=ovr", "t"));
    expect(response.headers.get("x-middleware-rewrite"))
      .toBe("http://api.internal:8000/api/teams/4/roster?sort=ovr");
    // A request id for the API's logs (passed on as a request header).
    expect(response.headers.get("x-middleware-request-x-request-id")).toMatch(/^[0-9a-f-]{36}$/);
  });

  it("or at API_HOSTPORT, a private network's host:port", () => {
    vi.stubEnv("API_URL", "");
    vi.stubEnv("API_HOSTPORT", "dynasty-api:10000");
    expect(proxy(request("/api/health")).headers.get("x-middleware-rewrite"))
      .toBe("http://dynasty-api:10000/api/health");
  });

  it("sends visitors without a session to sign in, and back afterwards", () => {
    const response = proxy(request("/games/7/watch?play=2"));
    expect(response.status).toBe(307);
    expect(response.headers.get("location"))
      .toBe("http://localhost:3000/signin?next=%2Fgames%2F7%2Fwatch%3Fplay%3D2");
    expect(proxy(request("/")).headers.get("location")).toBe("http://localhost:3000/signin");
  });

  it("lets signed-in visitors and the sign-in pages through", () => {
    for (const response of [proxy(request("/roster", "t")), proxy(request("/signin")),
      proxy(request("/reset-password?token=x")), proxy(request("/forgot-password"))]) {
      expect(response.headers.get("x-middleware-next")).toBe("1");
    }
  });
});
