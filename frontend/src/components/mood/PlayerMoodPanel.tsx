import type { PlayerMood } from "@/lib/types";
import { MoodMeter } from "./MoodMeter";

/**
 * A player's personality and mood: his two traits and what they mean, then the mood he
 * carried into the season and what this season has done to it, part by part.
 */
export function PlayerMoodPanel({ mood }: { mood: PlayerMood }) {
  return (
    <section className="panel space-y-4 p-6" aria-label="Personality and mood">
      <h2 className="eyebrow">Personality and mood</h2>
      <div className="grid gap-6 md:grid-cols-2">
        <dl className="space-y-2 text-sm">
          <div>
            <dt className="font-semibold">{mood.drive_label}</dt>
            <dd className="text-mist">Drive: {mood.drive_means}.</dd>
          </div>
          <div>
            <dt className="font-semibold">{mood.temperament_label}</dt>
            <dd className="text-mist">Temperament: {mood.temperament_means}.</dd>
          </div>
        </dl>
        <div>
          <div className="flex items-baseline justify-between text-sm">
            <span className="font-semibold">{mood.label}</span>
            <span className="stat-number text-2xl">{mood.mood}</span>
          </div>
          <MoodMeter label="Mood" value={mood.mood} />
          <ul aria-label="What moved his mood" className="mt-2 space-y-0.5 text-xs">
            <li className="flex justify-between gap-2">
              <span className="text-mist">Coming into the season</span>
              <span className="tabular-nums">{mood.base}</span>
            </li>
            {mood.parts.map(([what, change]) => (
              <li key={what} className="flex justify-between gap-2">
                <span className="text-mist">{what}</span>
                <span className={`tabular-nums ${change > 0 ? "text-emerald-300" : "text-rose-300"}`}>
                  {change > 0 ? `+${change}` : change}
                </span>
              </li>
            ))}
          </ul>
        </div>
      </div>
    </section>
  );
}
