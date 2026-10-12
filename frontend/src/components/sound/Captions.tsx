"use client";

import { captionAt, type CommentaryLine } from "@/lib/commentary";

/**
 * The commentary as captions (docs/design/sound.md §4), over the bottom of the viewer:
 * the line being said, for a few seconds. A polite live region, so a screen reader can
 * follow the call.
 */
export function Captions({ lines, time }: { lines: CommentaryLine[]; time: number }) {
  const line = captionAt(lines, time);
  return (
    <div aria-live="polite" aria-label="Commentary" role="log"
      className="pointer-events-none absolute inset-x-0 bottom-14 flex justify-center px-3">
      {line && (
        <p key={`${line.t}-${line.text}`}
          className="max-w-[60%] rounded-md bg-ink-950/85 px-3 py-1 text-center text-sm shadow-lg ring-1 ring-white/10">
          <span className="sr-only">{line.voice === "play" ? "Play-by-play: " : "Analyst: "}</span>
          <span className={line.voice === "color" ? "text-gold" : "text-chalk"}>{line.text}</span>
        </p>
      )}
    </div>
  );
}
