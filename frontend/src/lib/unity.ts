/**
 * The Unity renderer's side of the bridge (docs/design/depth-and-unity.md §4.1; Unity's is
 * unity/Assets/Dynasty/Runtime/Bridge.cs). The WebGL build is served from /unity/ when it's
 * been built (`make unity-build`, or CI); /unity/build.json names its files.
 *
 * The page keeps the playhead and the cameras: each frame it sends the time and the camera
 * (three.js scene coordinates), and Unity draws the play from the timeline it was given.
 */

import type { CameraShot } from "@/components/field/layout";
import type { Kit } from "@/components/field/players/kit";
import type { PlayTimeline } from "@/components/field/playback/timeline";

const BASE = "/unity/";
const READY_TIMEOUT = 45_000; // ms for the download, the start-up and the stage

export interface UnityBuild { loader: string; data: string; framework: string; code: string }

let build: Promise<UnityBuild | null> | null = null;

/** The installed build, or null when there isn't one (the Unity renderer is then off). */
export function unityBuild(): Promise<UnityBuild | null> {
  build ??= fetch(`${BASE}build.json`, { cache: "no-cache" })
    .then(async (r) => {
      if (r.ok) return (await r.json()) as UnityBuild;
      // Not installed: the app's 404 page streams, so drop it rather than leave the request
      // open (it would keep the page from ever going network-idle).
      await r.body?.cancel().catch(() => {});
      return null;
    })
    .catch(() => null);
  return build;
}

/** (Tests: forget the cached answer.) */
export function resetUnityBuild() { build = null; }

interface UnityInstance {
  SendMessage(object: string, method: string, value?: string): void;
  Quit(): Promise<void>;
}

declare global {
  interface Window {
    createUnityInstance?: (canvas: HTMLCanvasElement, config: Record<string, unknown>,
                           onProgress?: (progress: number) => void) => Promise<UnityInstance>;
  }
}

export interface UnityEvent { type: "ready" | "loaded" | "error"; detail: string }

/** A running Unity viewer. */
export interface UnityPlayer {
  /** The field as the page paints it (a base64 PNG), and the home fans' colors. */
  setField(png: string, crowd: string[]): void;
  /** A new play: its timeline, and each team's uniform by team id. */
  loadPlay(timeline: PlayTimeline, kits: Record<number, Kit>): void;
  /** This frame's playhead and camera. */
  setFrame(time: number, camera: CameraShot): void;
  quit(): Promise<void>;
}

/** The frame message: "t,px,py,pz,tx,ty,tz,fov" (Bridge.cs Frame.Parse). */
export function frameMessage(time: number, camera: CameraShot): string {
  return [time, ...camera.position, ...camera.target, camera.fov].map((n) => +n.toFixed(4)).join(",");
}

function loadScript(src: string): Promise<void> {
  if (window.createUnityInstance) return Promise.resolve();
  return new Promise((resolve, reject) => {
    const script = document.createElement("script");
    script.src = src;
    script.async = true;
    script.onload = () => resolve();
    script.onerror = () => reject(new Error("The Unity loader didn't download."));
    document.body.appendChild(script);
  });
}

/** Starts Unity on `canvas`; resolves once its stage is ready. `onEvent` hears every
 * later message (a play loaded, an error). */
export async function startUnity(canvas: HTMLCanvasElement, files: UnityBuild,
                                 onEvent: (event: UnityEvent) => void,
                                 onProgress?: (progress: number) => void): Promise<UnityPlayer> {
  let settle: { resolve: () => void; reject: (e: Error) => void } | null = null;
  const ready = new Promise<void>((resolve, reject) => { settle = { resolve, reject }; });
  const listener = (e: Event) => {
    const event = (e as CustomEvent<UnityEvent>).detail;
    if (event.type === "ready") settle?.resolve();
    else if (event.type === "error" && settle) settle.reject(new Error(event.detail));
    onEvent(event);
  };
  window.addEventListener("dynasty-unity", listener);
  let instance: UnityInstance | null = null;
  try {
    await loadScript(BASE + files.loader);
    instance = await window.createUnityInstance!(canvas, {
      dataUrl: BASE + files.data, frameworkUrl: BASE + files.framework, codeUrl: BASE + files.code,
      companyName: "Dynasty Football", productName: "Dynasty Football 3D", productVersion: "1",
      // Keys stay with the page (the viewer's controls), not the canvas.
      keyboardListeningElement: canvas,
      devicePixelRatio: Math.min(window.devicePixelRatio || 1, 2),
    }, onProgress);
    let timer: ReturnType<typeof setTimeout> | undefined;
    await Promise.race([ready, new Promise((_, reject) => {
      timer = setTimeout(() => reject(new Error("Unity didn't start in time.")), READY_TIMEOUT);
    })]).finally(() => clearTimeout(timer));
  } catch (error) {
    window.removeEventListener("dynasty-unity", listener);
    await instance?.Quit().catch(() => {});
    throw error;
  }
  settle = null;
  const unity = instance;
  return {
    setField(png, crowd) {
      unity.SendMessage("Bridge", "SetField", JSON.stringify({ image: png, crowd }));
    },
    loadPlay(timeline, kits) {
      unity.SendMessage("Bridge", "LoadPlay", JSON.stringify({ timeline, kits }));
    },
    setFrame(time, camera) {
      unity.SendMessage("Bridge", "SetFrame", frameMessage(time, camera));
    },
    async quit() {
      window.removeEventListener("dynasty-unity", listener);
      await unity.Quit().catch(() => {});
    },
  };
}
