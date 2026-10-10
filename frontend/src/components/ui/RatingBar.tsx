import { ratingTier, TIER_BAR } from "@/lib/format";

export function RatingBar({
  label,
  value,
  emphasis = false,
}: {
  label: string;
  value: number;
  emphasis?: boolean;
}) {
  return (
    <div className="grid grid-cols-[minmax(0,1fr)_2rem] items-center gap-x-3 gap-y-1">
      <span className={`truncate text-xs ${emphasis ? "font-medium text-chalk" : "text-mist"}`}>
        {label}
      </span>
      <span className="stat-number text-right text-sm">{value}</span>
      <div
        className="col-span-2 h-1.5 overflow-hidden rounded-full bg-white/[0.06]"
        role="meter"
        aria-label={label}
        aria-valuenow={value}
        aria-valuemin={0}
        aria-valuemax={99}
      >
        <div
          className={`h-full rounded-full ${TIER_BAR[ratingTier(value)]} ${emphasis ? "" : "opacity-70"}`}
          style={{ width: `${Math.max(2, (value / 99) * 100)}%` }}
        />
      </div>
    </div>
  );
}
