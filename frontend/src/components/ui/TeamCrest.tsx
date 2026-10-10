import type { TeamSummary } from "@/lib/types";

/** Procedural shield crest from team colours — placeholder until real team art exists. */
export function TeamCrest({
  team,
  size = 40,
}: {
  team: Pick<TeamSummary, "abbreviation" | "primary_color" | "secondary_color" | "full_name">;
  size?: number;
}) {
  const id = `crest-${team.abbreviation}`;
  return (
    <svg
      width={size}
      height={size * 1.15}
      viewBox="0 0 40 46"
      role="img"
      aria-label={`${team.full_name} crest`}
      className="shrink-0 drop-shadow-[0_4px_10px_rgb(0_0_0/0.45)]"
    >
      <defs>
        <linearGradient id={id} x1="0" y1="0" x2="0" y2="1">
          <stop offset="0" stopColor={team.primary_color} stopOpacity="1" />
          <stop offset="1" stopColor={team.primary_color} stopOpacity="0.75" />
        </linearGradient>
      </defs>
      <path
        d="M20 1.5 37 7v15.5C37 33 29.5 40.5 20 44.5 10.5 40.5 3 33 3 22.5V7L20 1.5Z"
        fill={`url(#${id})`}
        stroke={team.secondary_color}
        strokeWidth="2"
      />
      <path d="M3.5 15h33" stroke={team.secondary_color} strokeOpacity="0.35" strokeWidth="1" />
      <text
        x="20"
        y="29"
        textAnchor="middle"
        fontSize={team.abbreviation.length > 2 ? 11.5 : 14}
        fontWeight="800"
        fontFamily="var(--font-barlow), sans-serif"
        fill={team.secondary_color}
        letterSpacing="0.5"
      >
        {team.abbreviation}
      </text>
    </svg>
  );
}
