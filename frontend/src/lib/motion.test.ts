import { act, renderHook } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { usePrefersReducedMotion } from "./motion";

afterEach(() => vi.unstubAllGlobals());

describe("usePrefersReducedMotion", () => {
  it("follows the system setting as it changes", () => {
    const listeners = new Set<() => void>();
    let reduce = false;
    vi.stubGlobal("matchMedia", (query: string) => ({
      get matches() { return query === "(prefers-reduced-motion: reduce)" && reduce; },
      addEventListener: (_: string, fn: () => void) => listeners.add(fn),
      removeEventListener: (_: string, fn: () => void) => listeners.delete(fn),
    }));
    const { result, unmount } = renderHook(() => usePrefersReducedMotion());
    expect(result.current).toBe(false);
    act(() => {
      reduce = true;
      listeners.forEach((fn) => fn());
    });
    expect(result.current).toBe(true);
    unmount();
    expect(listeners.size).toBe(0);
  });

  it("is off where matchMedia doesn't exist", () => {
    vi.stubGlobal("matchMedia", undefined);
    expect(renderHook(() => usePrefersReducedMotion()).result.current).toBe(false);
  });
});
