import { TeamCrest } from "@/components/ui/TeamCrest";
import type { FrontOffice } from "@/lib/types";

const STYLE: Record<NonNullable<FrontOffice["direction"]>, string> = {
  contend: "bg-emerald-400/15 text-emerald-300",
  middle: "bg-white/[0.06] text-chalk",
  rebuild: "bg-amber-300/15 text-amber-200",
};

/**
 * Where every front office is going: each AI team's direction (decided each offseason) and
 * why, and who runs the members' teams.
 */
export function FrontOffices({ offices }: { offices: FrontOffice[] }) {
  const ordered = [...offices].sort((a, b) =>
    (a.manager ? 0 : 1) - (b.manager ? 0 : 1) || a.team.full_name.localeCompare(b.team.full_name));
  return (
    <section className="panel p-5" aria-label="Front offices">
      <h2 className="eyebrow mb-1">Front offices</h2>
      <p className="mb-3 text-xs text-mist">
        Each offseason, every AI team decides where it&apos;s going, and builds to match.
      </p>
      <ul className="space-y-1 text-sm">
        {ordered.map((office) => (
          <li key={office.team.id}>
            {office.manager ? (
              <div className="flex items-center gap-2 py-0.5">
                <TeamCrest team={office.team} size={18} />
                <span className="flex-1 truncate">{office.team.full_name}</span>
                <span className="text-xs text-mist">Run by {office.manager}</span>
              </div>
            ) : (
              <details>
                <summary className="flex cursor-pointer items-center gap-2 py-0.5">
                  <TeamCrest team={office.team} size={18} />
                  <span className="flex-1 truncate">{office.team.full_name}</span>
                  <span className={`rounded px-1.5 py-0.5 text-[11px] font-semibold ${STYLE[office.direction ?? "middle"]}`}>
                    {office.label}
                  </span>
                </summary>
                <ul className="mb-1 ml-7 list-disc pl-4 text-xs text-mist">
                  {office.reasons.map((why) => <li key={why}>{why}</li>)}
                </ul>
              </details>
            )}
          </li>
        ))}
      </ul>
    </section>
  );
}
