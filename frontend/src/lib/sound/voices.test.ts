import { afterEach, describe, expect, it, vi } from "vitest";
import type { CommentaryLine } from "@/lib/commentary";
import { Speaker } from "./speaker";
import { DELIVERY, firstClause, pickVoices, speakingTime, speechPlan } from "./voices";

const voice = (name: string, lang = "en-US", localService = true) => ({ name, lang, localService });

describe("the booth's voices", () => {
  it("are two different English voices, local first, chosen the same way every time", () => {
    const available = [voice("Zed"), voice("Amélie", "fr-FR"), voice("Cloud Ann", "en-GB", false), voice("Alex")];
    expect(pickVoices(available)).toEqual({ play: voice("Alex"), color: voice("Zed") });
    expect(pickVoices([...available].reverse())).toEqual(pickVoices(available));
  });

  it("share one voice when that's all there is, or none at all", () => {
    expect(pickVoices([voice("Alex")])).toEqual({ play: voice("Alex"), color: voice("Alex") });
    expect(pickVoices([voice("Amélie", "fr-FR")])!.play.name).toBe("Amélie"); // (better than silence)
    expect(pickVoices([])).toBeNull();
  });

  it("sound like two people even in one voice: the announcer quicker and higher", () => {
    expect(DELIVERY.play.rate).toBeGreaterThan(DELIVERY.color.rate);
    expect(DELIVERY.play.pitch).toBeGreaterThan(DELIVERY.color.pitch);
  });
});

describe("pacing the call", () => {
  const line = (t: number, text: string, v: "play" | "color" = "play"): CommentaryLine => ({ t, voice: v, text });

  it("takes longer to say a longer line", () => {
    expect(speakingTime("Gains six.", "play")).toBeLessThan(speakingTime("Gains six, brought down by Banks.", "play"));
  });

  it("cuts a line to its first clause", () => {
    expect(firstClause("Fires for Wolfe…")).toBe("Fires for Wolfe");
    expect(firstClause("Gains 6, brought down by Banks.")).toBe("Gains 6");
    expect(firstClause("Touchdown!")).toBe("Touchdown!");
  });

  it("says what fits before the next line, shortens what doesn't, and leaves the rest to captions", () => {
    const lines = [
      line(1, "Quarles back to throw…"),
      line(1.6, "Fires for Wolfe, who has a step on the corner down the sideline…"), // 1.2 s of room
      line(2.8, "Caught at the 30, and the defense is scrambling to get back in position now!"), // 0.1 s
      line(2.9, "Brought down by Banks."),
      line(5, "That's six catches for Wolfe today.", "color"),
    ];
    const plan = speechPlan(lines, 4.5);
    // The drop-back has no room before the throw, so the call skips to the action; the
    // catch is cut off by the tackle a tenth of a second later; the analyst has time.
    expect(plan.map((l) => l.text)).toEqual([
      "Fires for Wolfe", "Brought down by Banks.", "That's six catches for Wolfe today.",
    ]);
    expect(plan.map((l) => l.t)).toEqual([1.6, 2.9, 5]); // (still on their moments)
  });
});

describe("the speaker", () => {
  afterEach(() => { delete window.dynastySound; });

  function fakeSynth() {
    return {
      cancel: vi.fn(), speak: vi.fn(),
      getVoices: () => [voice("Alex"), voice("Zed")] as unknown as SpeechSynthesisVoice[],
    };
  }
  class FakeUtterance {
    voice: unknown = null; rate = 1; pitch = 1; volume = 1;
    onstart?: () => void; onend?: () => void; onerror?: () => void;
    constructor(public text: string) {}
  }

  it("says each line in its voice, cutting off the last, and lowers the crowd while talking", () => {
    vi.stubGlobal("SpeechSynthesisUtterance", FakeUtterance);
    window.dynastySound = { state: "running", played: [], spoken: [] };
    const synth = fakeSynth();
    const talking = vi.fn();
    const speaker = new Speaker(synth as unknown as SpeechSynthesis, talking);
    speaker.say({ t: 1, voice: "color", text: "What a drive." }, 0.6);
    expect(synth.cancel).toHaveBeenCalled(); // (never falls behind: a new line cuts off the last)
    const said = synth.speak.mock.calls[0][0] as FakeUtterance;
    expect(said.text).toBe("What a drive.");
    expect((said.voice as { name: string }).name).toBe("Zed"); // the analyst
    expect([said.rate, said.pitch, said.volume]).toEqual([DELIVERY.color.rate, DELIVERY.color.pitch, 0.6]);
    said.onstart!();
    expect(talking).toHaveBeenLastCalledWith(true);
    said.onend!();
    expect(talking).toHaveBeenLastCalledWith(false);
    expect(window.dynastySound.spoken).toEqual(["What a drive."]);
    speaker.stop();
    expect(talking).toHaveBeenLastCalledWith(false);
    vi.unstubAllGlobals();
  });
});
