/**
 * Spoken commentary (docs/design/sound.md §4): which of the device's voices call the game,
 * how fast a line is said, and which lines fit before the next one must start (a line
 * that would run over the next is cut to its first clause, or dropped). Pure.
 */

import type { CommentaryLine, Voice } from "@/lib/commentary";

/** The little we need of a SpeechSynthesisVoice. */
export interface VoiceLike { name: string; lang: string; default?: boolean; localService?: boolean }

/** Two voices for the booth: the announcer and the analyst, different if the device has
 * two English ones (local voices first, then by name, so the choice is stable). Null when
 * there are none. */
export function pickVoices<V extends VoiceLike>(available: V[]): { play: V; color: V } | null {
  const english = available.filter((v) => v.lang.toLowerCase().startsWith("en"));
  const pool = (english.length ? english : available).slice().sort((a, b) =>
    Number(b.localService ?? false) - Number(a.localService ?? false) || a.name.localeCompare(b.name));
  if (!pool.length) return null;
  return { play: pool[0], color: pool[1] ?? pool[0] };
}

/** How the two voices sound: the announcer a little quicker and higher, the analyst
 * slower and lower (so one voice still reads as two people). */
export const DELIVERY: Record<Voice, { rate: number; pitch: number }> = {
  play: { rate: 1.12, pitch: 1.05 },
  color: { rate: 0.98, pitch: 0.85 },
};

const WORDS_PER_SECOND = 3.0; // at rate 1 (a brisk broadcast pace)

/** Roughly how long a line takes to say. */
export function speakingTime(text: string, voice: Voice): number {
  const words = text.split(/\s+/).filter(Boolean).length;
  return words / (WORDS_PER_SECOND * DELIVERY[voice].rate) + 0.1;
}

/** The first clause of a line ("Gains 6, brought down by Banks" → "Gains 6"). */
export function firstClause(text: string): string {
  const cut = text.search(/…|,|—/);
  return (cut > 0 ? text.slice(0, cut) : text).trim();
}

/**
 * What's actually said: each line keeps its moment but must be done before the next line
 * starts; the last (usually the analyst, after the whistle) has until the next play,
 * about five seconds. A line that's too long is cut to its first clause; if that's still
 * too long, it's left to the captions (the call skips ahead to the action).
 */
export function speechPlan(lines: CommentaryLine[], end: number): CommentaryLine[] {
  const plan: CommentaryLine[] = [];
  lines.forEach((line, i) => {
    const next = lines[i + 1];
    const room = (next ? next.t : end + 5) - line.t + 0.3;
    if (speakingTime(line.text, line.voice) <= room) return plan.push(line);
    const short = firstClause(line.text);
    if (short !== line.text && speakingTime(short, line.voice) <= room) plan.push({ ...line, text: short });
  });
  return plan;
}
