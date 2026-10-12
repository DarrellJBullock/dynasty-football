/**
 * The booth's voices: the browser's speech synthesis saying the commentary (docs/design/
 * sound.md §4). One line at a time: a new line cuts off one still going, so the voices
 * never fall behind the play. Tells the engine while someone's talking, to lower the crowd.
 */

import type { CommentaryLine } from "@/lib/commentary";
import { DELIVERY, pickVoices } from "./voices";

export class Speaker {
  constructor(private readonly synth: SpeechSynthesis, private readonly onTalking: (talking: boolean) => void) {}

  /** The speaker, or null where the browser can't speak. */
  static create(onTalking: (talking: boolean) => void): Speaker | null {
    if (typeof window === "undefined" || !window.speechSynthesis || typeof SpeechSynthesisUtterance === "undefined") {
      return null;
    }
    return new Speaker(window.speechSynthesis, onTalking);
  }

  say(line: CommentaryLine, volume: number) {
    this.synth.cancel();
    const utterance = new SpeechSynthesisUtterance(line.text);
    const voices = pickVoices(this.synth.getVoices());
    if (voices) utterance.voice = voices[line.voice];
    utterance.rate = DELIVERY[line.voice].rate;
    utterance.pitch = DELIVERY[line.voice].pitch;
    utterance.volume = Math.max(0, Math.min(1, volume));
    utterance.onstart = () => this.onTalking(true);
    utterance.onend = () => this.onTalking(false);
    utterance.onerror = () => this.onTalking(false);
    const probe = window.dynastySound;
    if (probe) probe.spoken = [...probe.spoken.slice(-19), line.text];
    this.synth.speak(utterance);
  }

  stop() {
    this.synth.cancel();
    this.onTalking(false);
  }
}
