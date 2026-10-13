import type { Owner, OwnerGoal, OwnerPart } from "@/lib/types";

const STATUS: Record<OwnerGoal["status"], { label: string; style: string }> = {
  met: { label: "Met", style: "bg-emerald-400/15 text-emerald-300" },
  missed: { label: "Missed", style: "bg-rose-400/15 text-rose-300" },
  on_track: { label: "On track", style: "bg-white/[0.06] text-chalk" },
  behind: { label: "Behind", style: "bg-amber-300/15 text-amber-200" },
};

const SITUATION: Record<NonNullable<Owner["situation"]>, string> = {
  contender: "a contender", middle: "in the middle of the league", rebuilding: "rebuilding",
};

function Meter({ label, value }: { label: string; value: number }) {
  const tone = value < 30 ? "bg-rose-400" : value < 55 ? "bg-amber-300" : "bg-emerald-400";
  return (
    <div>
      <div className="flex items-baseline justify-between text-xs">
        <span className="text-mist">{label}</span>
        <span className="stat-number text-lg">{value}</span>
      </div>
      <div role="meter" aria-label={label} aria-valuemin={0} aria-valuemax={100} aria-valuenow={value}
        className="mt-1 h-1.5 overflow-hidden rounded bg-white/10">
        <div className={`h-full ${tone}`} style={{ width: `${value}%` }} />
      </div>
    </div>
  );
}

/** What moved a number, part by part ("Record +6, Made the playoffs +5"). */
function Parts({ label, parts }: { label: string; parts: OwnerPart[] }) {
  if (parts.length === 0) return null;
  return (
    <ul aria-label={label} className="mt-1 space-y-0.5 text-xs">
      {parts.map(([what, change]) => (
        <li key={what} className="flex justify-between gap-2">
          <span className="text-mist">{what}</span>
          <span className={`tabular-nums ${change > 0 ? "text-emerald-300" : change < 0 ? "text-rose-300" : "text-mist"}`}>
            {change > 0 ? `+${change}` : change}
          </span>
        </li>
      ))}
    </ul>
  );
}

/**
 * The owner: what they want and how patient they are, this season's goals and how they're
 * going, their confidence in you and the fans' mood (with what moved each), and the last
 * season's review.
 */
export function OwnerCard({ owner }: { owner: Owner }) {
  const review = owner.last_review;
  return (
    <section className="panel space-y-4 p-5" aria-label="The owner">
      <header className="flex flex-wrap items-baseline justify-between gap-2">
        <div>
          <h2 className="eyebrow">The owner</h2>
          <p className="mt-1 text-sm">
            <span className="font-semibold">{owner.name}</span> {owner.wants}
            <span className="text-mist"> · patience {owner.patience} of 5 · {owner.market} market</span>
          </p>
        </div>
        {owner.hot_seat && (
          <p role="status" className="rounded bg-rose-400/15 px-2 py-1 text-xs font-semibold text-rose-200">
            Hot seat: the owner is losing patience
          </p>
        )}
      </header>

      <div className="grid gap-6 md:grid-cols-3">
        <div>
          <h3 className="text-sm font-semibold">
            {owner.season_year ? `${owner.season_year} goals` : "Goals"}
          </h3>
          {owner.goals.length === 0 ? (
            <p className="mt-1 text-xs text-mist">The owner sets the season&apos;s goals when the preseason opens.</p>
          ) : (
            <>
              {owner.situation && (
                <p className="mt-1 text-xs text-mist">Set with the roster {SITUATION[owner.situation]}.</p>
              )}
              <ul className="mt-2 space-y-1.5 text-sm" aria-label="Goals">
                {owner.goals.map((g) => (
                  <li key={g.label} className="flex items-center justify-between gap-2">
                    <span>{g.label}{g.primary && <span className="text-xs text-gold"> · main goal</span>}</span>
                    <span className={`rounded px-1.5 py-0.5 text-[11px] font-semibold ${STATUS[g.status].style}`}>
                      {STATUS[g.status].label}
                    </span>
                  </li>
                ))}
              </ul>
            </>
          )}
        </div>

        <div>
          <Meter label="Owner confidence" value={owner.confidence} />
          <p className="mt-1 text-xs text-mist">The owner judges you on the goals and the fans when the season ends.</p>
        </div>

        <div>
          <Meter label="Fan mood" value={owner.fan_mood} />
          <Parts label="What moved the fans this season" parts={owner.fan_parts} />
        </div>
      </div>

      {review && (
        <details className="border-t border-white/5 pt-3 text-sm">
          <summary className="cursor-pointer">
            {review.year} review: the owner {review.verdict}
            {review.confidence_before !== null && review.confidence_after !== null && (
              <span className="text-mist"> (confidence {review.confidence_before} → {review.confidence_after})</span>
            )}
          </summary>
          <div className="mt-2 grid gap-4 md:grid-cols-2">
            <Parts label="What moved the owner" parts={review.confidence_parts} />
            <div>
              <p className="text-xs text-mist">Fan mood {review.fan_mood_before} → {review.fan_mood_after}</p>
              <Parts label="What moved the fans" parts={review.fan_parts} />
            </div>
          </div>
        </details>
      )}
    </section>
  );
}
