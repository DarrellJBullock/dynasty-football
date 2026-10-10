import { ratingTier, TIER_STYLES } from "@/lib/format";

const SIZES = {
  sm: "h-6 min-w-8 text-sm",
  md: "h-8 min-w-10 text-lg",
  lg: "h-12 min-w-14 text-3xl",
};

export function OvrBadge({
  value,
  size = "sm",
  label,
}: {
  value: number;
  size?: keyof typeof SIZES;
  label?: string;
}) {
  const tier = ratingTier(value);
  return (
    <span
      className={`stat-number inline-flex items-center justify-center rounded-md px-1.5 ring-1 ring-inset ${SIZES[size]} ${TIER_STYLES[tier]}`}
      title={label ?? `${value} overall (${tier})`}
      data-tier={tier}
    >
      {value}
    </span>
  );
}
