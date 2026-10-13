/** A mood (0-100) as a meter, colored by how it's going. */
export function MoodMeter({ label, value }: { label: string; value: number }) {
  const tone = value < 35 ? "bg-rose-400" : value < 55 ? "bg-amber-300" : "bg-emerald-400";
  return (
    <div role="meter" aria-label={label} aria-valuemin={0} aria-valuemax={100} aria-valuenow={value}
      className="h-1.5 overflow-hidden rounded bg-white/10">
      <div className={`h-full ${tone}`} style={{ width: `${value}%` }} />
    </div>
  );
}
