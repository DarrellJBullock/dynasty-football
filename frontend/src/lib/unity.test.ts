import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import type { PlayTimeline } from "@/components/field/playback/timeline";
import { frameMessage, resetUnityBuild, startUnity, unityBuild, type UnityBuild } from "./unity";

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
