"use client";

import dynamic from "next/dynamic";
import { useCallback, useEffect, useState } from "react";
import { unityBuild } from "@/lib/unity";

/** The Unity renderer (docs/design/depth-and-unity.md §4), loaded only when chosen. */
export const UnityPlayScene = dynamic(() => import("./UnityPlayScene"), {
  ssr: false,
  loading: () => <div className="h-full w-full animate-pulse bg-turf/10" />,
});

export type Renderer = "classic" | "unity";
const RENDERERS: { key: Renderer; label: string }[] = [
  { key: "classic", label: "Classic" }, { key: "unity", label: "Unity" },
];
export const RENDERER_KEY = "dynasty.renderer"; // the visitor's choice, in localStorage

/**
 * Which renderer the 3D viewers use, shared by the Watch page and Coach Mode: Classic, or
 * Unity when its build is installed. The choice is remembered in the browser; if Unity
 * fails, it's back to Classic, here and next time, with the reason.
 */
export function useRenderer() {
  const [renderer, setRendererState] = useState<Renderer>("classic");
  const [installed, setInstalled] = useState(false);
  const [problem, setProblem] = useState<string | null>(null);
  useEffect(() => {
    let live = true;
    void unityBuild().then((files) => {
      if (!live || !files) return;
      setInstalled(true);
      try {
        if (localStorage.getItem(RENDERER_KEY) === "unity") setRendererState("unity");
      } catch { /* storage blocked: start on Classic */ }
    });
    return () => { live = false; };
  }, []);
  const setRenderer = useCallback((choice: Renderer) => {
    setRendererState(choice);
    setProblem(null);
    try { localStorage.setItem(RENDERER_KEY, choice); } catch { /* not remembered */ }
  }, []);
  const onUnityError = useCallback((message: string) => {
    setRendererState("classic");
    setProblem(message);
    try { localStorage.setItem(RENDERER_KEY, "classic"); } catch { /* not remembered */ }
  }, []);
  return { renderer, setRenderer, installed, problem, onUnityError };
}

export function RendererSwitch({ renderer, installed, onChange, className = "" }: {
  renderer: Renderer; installed: boolean; onChange: (choice: Renderer) => void; className?: string;
}) {
  return (
    <div role="group" aria-label="Renderer" className={`flex gap-1 rounded-lg bg-white/[0.03] p-1 ${className}`}>
      {RENDERERS.map(({ key, label }) => (
        <button key={key} type="button" aria-pressed={renderer === key}
          disabled={key === "unity" && !installed}
          title={key === "unity" && !installed ? "The Unity viewer isn't installed on this server" : undefined}
          className={`rounded-md px-2 py-0.5 text-[11px] font-semibold disabled:opacity-40 ${
            renderer === key ? "bg-white/10 text-chalk" : "text-mist hover:text-chalk"}`}
          onClick={() => onChange(key)}>
          {label}
        </button>
      ))}
    </div>
  );
}

/** Why the page went back to Classic. */
export function UnityProblem({ problem }: { problem: string | null }) {
  if (!problem) return null;
  return (
    <p role="alert" className="text-xs text-amber-300">
      The Unity viewer stopped: {problem} Showing the classic viewer.
    </p>
  );
}
