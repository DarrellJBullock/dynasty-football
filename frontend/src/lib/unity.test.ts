import { afterEach, beforeEach, describe, expect, it, vi, type Mock } from "vitest";
import type { PlayTimeline } from "@/components/field/playback/timeline";
import {
  frameMessage, leaseUnity, resetUnityBuild, resetUnitySession, startUnity, unityBuild, type UnityBuild,
} from "./unity";

const FILES: UnityBuild = { loader: "Build/unity.loader.js", data: "Build/unity.data.unityweb",
  framework: "Build/unity.framework.js.unityweb", code: "Build/unity.wasm.unityweb" };

function say(type: string, detail = "") {
  window.dispatchEvent(new CustomEvent("dynasty-unity", { detail: { type, detail } }));
}

describe("the Unity bridge", () => {
  beforeEach(() => resetUnityBuild());
  afterEach(() => {
    vi.unstubAllGlobals();
    delete window.createUnityInstance;
  });

  it("finds the installed build, or says there isn't one", async () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue({ ok: true, json: async () => FILES }));
    expect(await unityBuild()).toEqual(FILES);
    expect(fetch).toHaveBeenCalledWith("/unity/build.json", { cache: "no-cache" });
    await unityBuild();
    expect(fetch).toHaveBeenCalledTimes(1); // asked once

    resetUnityBuild();
    const cancel = vi.fn().mockResolvedValue(undefined);
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue({ ok: false, body: { cancel } }));
    expect(await unityBuild()).toBeNull();
    expect(cancel).toHaveBeenCalled(); // the 404 page isn't left streaming
    resetUnityBuild();
    vi.stubGlobal("fetch", vi.fn().mockRejectedValue(new Error("offline")));
    expect(await unityBuild()).toBeNull();
  });

  it("sends the playhead and the camera as one compact frame", () => {
    expect(frameMessage(1.234567, { position: [10, 20.5, 62.66666], target: [-4, 0, 0], fov: 26 }))
      .toBe("1.2346,10,20.5,62.6667,-4,0,0,26");
  });

  it("starts Unity on the canvas, then loads plays and sends frames", async () => {
    const instance = { SendMessage: vi.fn(), Quit: vi.fn().mockResolvedValue(undefined) };
    window.createUnityInstance = vi.fn(async () => {
      setTimeout(() => say("ready"), 0);
      return instance;
    });
    const canvas = document.createElement("canvas");
    const events = vi.fn();
    const player = await startUnity(canvas, FILES, events);
    expect(window.createUnityInstance).toHaveBeenCalledWith(canvas, expect.objectContaining({
      dataUrl: "/unity/Build/unity.data.unityweb", codeUrl: "/unity/Build/unity.wasm.unityweb",
      keyboardListeningElement: canvas,
    }), undefined);

    player.setField("iVBORw0KGgo=", ["#123456", "#abcdef"]);
    expect(instance.SendMessage).toHaveBeenCalledWith("Bridge", "SetField",
      JSON.stringify({ image: "iVBORw0KGgo=", crowd: ["#123456", "#abcdef"] }));
    const timeline = { duration: 4 } as PlayTimeline;
    const kit = { jersey: "#123456", numbers: "#ffffff", pants: "#abcdef", helmet: "#123456", socks: "#123456" };
    player.loadPlay(timeline, { 1: kit });
    expect(instance.SendMessage).toHaveBeenCalledWith("Bridge", "LoadPlay", JSON.stringify({ timeline, kits: { 1: kit } }));
    player.setFrame(2, { position: [0, 1, 2], target: [3, 4, 5], fov: 30 });
    expect(instance.SendMessage).toHaveBeenLastCalledWith("Bridge", "SetFrame", "2,0,1,2,3,4,5,30");

    say("loaded", "22");
    expect(events).toHaveBeenLastCalledWith({ type: "loaded", detail: "22" });
    await player.quit();
    expect(instance.Quit).toHaveBeenCalled();
    say("error", "late");
    expect(events).not.toHaveBeenCalledWith({ type: "error", detail: "late" }); // not listening
  });

  it("fails when Unity reports an error before it's ready, and quits it", async () => {
    const instance = { SendMessage: vi.fn(), Quit: vi.fn().mockResolvedValue(undefined) };
    window.createUnityInstance = vi.fn(async () => {
      setTimeout(() => say("error", "No WebGL 2."), 0);
      return instance;
    });
    await expect(startUnity(document.createElement("canvas"), FILES, vi.fn())).rejects.toThrow("No WebGL 2.");
    expect(instance.Quit).toHaveBeenCalled();
  });
});

describe("one Unity for the page", () => {
  let instance: { SendMessage: Mock<(object: string, method: string, value?: string) => void>;
                  Quit: Mock<() => Promise<void>> };
  beforeEach(() => {
    resetUnitySession();
    instance = { SendMessage: vi.fn<(object: string, method: string, value?: string) => void>(),
                 Quit: vi.fn<() => Promise<void>>().mockResolvedValue(undefined) };
    window.createUnityInstance = vi.fn(async () => {
      setTimeout(() => say("ready"), 0);
      return instance;
    });
  });
  afterEach(() => {
    delete window.createUnityInstance;
    resetUnitySession();
  });
  const box = () => document.body.appendChild(document.createElement("div"));
  const sent = (method: string) => instance.SendMessage.mock.calls.filter(([, m]) => m === method).map(([, , v]) => v);

  it("starts once and moves its canvas to whichever viewer is shown, parking it between", async () => {
    const first = box();
    const a = leaseUnity(first, FILES, vi.fn());
    await a.player;
    const canvas = first.querySelector("canvas")!;
    expect(canvas.id).toBe("unity-canvas");
    expect(canvas).toHaveAttribute("aria-label", "3D play");

    a.release();
    expect(canvas.parentElement!.hidden).toBe(true); // parked, out of sight
    await Promise.resolve();
    expect(sent("SetActive")).toEqual(["1", "0"]);

    const second = box();
    const b = leaseUnity(second, FILES, vi.fn());
    await b.player;
    expect(second.querySelector("canvas")).toBe(canvas); // the same Unity
    expect(window.createUnityInstance).toHaveBeenCalledTimes(1);
    expect(sent("SetActive").at(-1)).toBe("1");
  });

  it("doesn't park a canvas the next viewer has already taken", async () => {
    const first = box();
    const a = leaseUnity(first, FILES, vi.fn());
    const second = box();
    const b = leaseUnity(second, FILES, vi.fn()); // (mounted before the first lets go)
    await b.player;
    a.release();
    expect(second.querySelector("canvas")).not.toBeNull();
  });

  it("paints a game's field once, and tells only the viewers still listening", async () => {
    const heard = vi.fn();
    const a = leaseUnity(box(), FILES, heard);
    const paint = vi.fn(() => "iVBORw0KGgo=");
    await a.setField("7", paint, ["#123456"]);
    await a.setField("7", paint, ["#123456"]);
    expect(paint).toHaveBeenCalledTimes(1);
    expect(sent("SetField")).toHaveLength(1);
    await a.setField("8", paint, ["#654321"]);
    expect(sent("SetField")).toHaveLength(2);

    say("loaded", "22");
    expect(heard).toHaveBeenCalledWith({ type: "loaded", detail: "22" });
    a.release();
    say("loaded", "22");
    expect(heard.mock.calls.filter(([e]) => e.type === "loaded")).toHaveLength(1);
  });

  it("tries again for the next viewer if Unity couldn't start", async () => {
    window.createUnityInstance = vi.fn(async () => {
      setTimeout(() => say("error", "No WebGL 2."), 0);
      return instance;
    });
    const a = leaseUnity(box(), FILES, vi.fn());
    await expect(a.player).rejects.toThrow("No WebGL 2.");
    window.createUnityInstance = vi.fn(async () => {
      setTimeout(() => say("ready"), 0);
      return instance;
    });
    await leaseUnity(box(), FILES, vi.fn()).player;
    expect(window.createUnityInstance).toHaveBeenCalledTimes(1); // (the new one)
  });
});
