"use client";

import type { SoundSettings } from "@/lib/sound/useGameSound";

/** Sound on or off, the volume, the effects and crowd, and captions (docs/design/sound.md §5). */
export function SoundControls({ settings, onChange }: {
  settings: SoundSettings;
  onChange: (change: Partial<SoundSettings>) => void;
}) {
  return (
    <div role="group" aria-label="Sound" className="flex flex-wrap items-center gap-2 text-xs text-mist">
      <button type="button" aria-pressed={settings.on}
        className={`rounded-md px-2 py-1 text-[11px] font-semibold ${
          settings.on ? "bg-white/10 text-chalk" : "text-mist hover:text-chalk"}`}
        onClick={() => onChange({ on: !settings.on })}>
        {settings.on ? "Sound on" : "Sound off"}
      </button>
      <button type="button" aria-pressed={settings.captions}
        className={`rounded-md px-2 py-1 text-[11px] font-semibold ${
          settings.captions ? "bg-white/10 text-chalk" : "text-mist hover:text-chalk"}`}
        onClick={() => onChange({ captions: !settings.captions })}>
        Captions
      </button>
      {settings.on && (
        <>
          <input type="range" aria-label="Volume" className="w-24 accent-gold" min={0} max={1} step={0.05}
            value={settings.volume} aria-valuetext={`${Math.round(settings.volume * 100)}%`}
            onChange={(e) => onChange({ volume: Number(e.target.value) })} />
          <label className="flex items-center gap-1">
            <input type="checkbox" checked={settings.effects} onChange={(e) => onChange({ effects: e.target.checked })} />
            Effects
          </label>
          <label className="flex items-center gap-1">
            <input type="checkbox" checked={settings.crowd} onChange={(e) => onChange({ crowd: e.target.checked })} />
            Crowd
          </label>
          <label className="flex items-center gap-1">
            <input type="checkbox" checked={settings.voices} onChange={(e) => onChange({ voices: e.target.checked })} />
            Commentary
          </label>
        </>
      )}
    </div>
  );
}
