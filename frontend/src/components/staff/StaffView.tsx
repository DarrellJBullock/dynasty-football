"use client";

import { useRouter } from "next/navigation";
import { PageHeader, Panel } from "@/components/ui/Panel";
import { TeamCrest } from "@/components/ui/TeamCrest";
import { formatMoney, formatRecord } from "@/lib/format";
import type { Coaches, StaffCareer, StaffMember, TeamStaff, TeamSummary } from "@/lib/types";

function ratingTone(rating: number): string {
  return rating >= 85 ? "text-gold" : rating >= 70 ? "text-emerald-300" : rating >= 55 ? "text-chalk" : "text-mist";
}

export function careerLine(c: StaffCareer): string {
  if (!c.seasons) return "First season";
  const parts = [`${c.seasons} season${c.seasons === 1 ? "" : "s"}`, formatRecord(c)];
  if (c.playoff_wins) parts.push(`${c.playoff_wins} playoff win${c.playoff_wins === 1 ? "" : "s"}`);
  if (c.titles) parts.push(`${c.titles} title${c.titles === 1 ? "" : "s"}`);
  if (c.coach_of_the_year) parts.push(`${c.coach_of_the_year}× Coach of the Year`);
  return parts.join(" · ");
}

/**
 * Staff: a team's head coach, coordinators, scout and trainer (ratings, contracts and
 * careers), and the league's head coaches with Coach of the Year by season.
 */
export function StaffView({ staff, coaches, teams, season }: {
  staff: TeamStaff; coaches: Coaches; teams: TeamSummary[]; season: number;
}) {
  const router = useRouter();
  const team = staff.team;
  return (
    <div className="mx-auto max-w-7xl">
      <PageHeader eyebrow="Staff" title={team.full_name}>
        <label className="flex items-center gap-2 text-sm">
          <span className="eyebrow">Team</span>
          <select className="field-input" value={team.id}
            onChange={(e) => router.push(`/staff?team=${e.target.value}`)}>
            {teams.map((t) => <option key={t.id} value={t.id}>{t.full_name}</option>)}
          </select>
        </label>
      </PageHeader>
      <div className="space-y-6">
        <section aria-label="Coaches and staff" className="grid gap-4 md:grid-cols-2 xl:grid-cols-3">
          {staff.members.map((m) => <Card key={m.id} member={m} season={season} />)}
        </section>
        <p className="text-sm text-mist">
          Staff payroll {formatMoney(staff.payroll)} a season. Ratings run 40–99; 50 is average.
        </p>

        <div className="grid gap-6 lg:grid-cols-[minmax(0,2fr)_minmax(0,1fr)]">
          <Panel title="Head coaches">
            <div className="overflow-x-auto">
              <table className="w-full min-w-[520px] text-sm" aria-label="Head coaches">
                <thead>
                  <tr className="text-left text-[10px] uppercase tracking-wider text-mist">
                    <th className="py-1 font-medium">Team</th>
                    <th className="font-medium">Coach</th>
                    <th className="text-right font-medium">Rating</th>
                    <th className="text-right font-medium">Career</th>
                  </tr>
                </thead>
                <tbody>
                  {coaches.head_coaches.map((c) => (
                    <tr key={c.id} className={`border-t border-white/5 ${c.team?.id === team.id ? "bg-gold/[0.06]" : ""}`}>
                      <td className="py-1.5">{c.team && <span className="flex items-center gap-2"><TeamCrest team={c.team} size={18} />{c.team.abbreviation}</span>}</td>
                      <td>{c.name}</td>
                      <td className={`text-right tabular-nums ${ratingTone(c.rating)}`}>{c.rating}</td>
                      <td className="text-right tabular-nums text-mist">
                        {c.career.seasons
                          ? `${formatRecord(c.career)}${c.career.titles ? ` · ${c.career.titles} title${c.career.titles === 1 ? "" : "s"}` : ""}`
                          : "—"}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </Panel>
          <Panel title="Coach of the Year">
            {coaches.coach_of_the_year.length === 0 ? (
              <p className="text-sm text-mist">Named when a season&apos;s champion is crowned: the head coach whose team improved most.</p>
            ) : (
              <ul className="space-y-2" aria-label="Coach of the Year by season">
                {coaches.coach_of_the_year.map((c) => (
                  <li key={c.year} className="flex items-center gap-2 text-sm">
                    <span className="w-10 tabular-nums text-mist">{c.year}</span>
                    <TeamCrest team={c.team} size={18} />
                    <span className="flex-1">{c.name}</span>
                    <span className="tabular-nums text-mist">{formatRecord(c)}</span>
                  </li>
                ))}
              </ul>
            )}
          </Panel>
        </div>
      </div>
    </div>
  );
}

function Card({ member, season }: { member: StaffMember; season: number }) {
  const left = member.contract_end - season + 1;
  return (
    <article className="panel p-5" aria-label={member.role_label}>
      <div className="flex items-start justify-between gap-3">
        <div>
          <div className="eyebrow">{member.role_label}</div>
          <h2 className="mt-1 font-display text-2xl font-bold uppercase">{member.name}</h2>
          <p className="text-sm text-mist">
            Age {member.age}{member.specialty && ` · ${member.specialty} specialist`}
          </p>
        </div>
        <div className="text-right">
          <div className={`stat-number text-3xl ${ratingTone(member.rating)}`}>{member.rating}</div>
          <div className="text-[10px] uppercase tracking-wider text-mist">Rating</div>
        </div>
      </div>
      <p className="mt-3 text-sm">{member.duty}</p>
      <p className="mt-1 text-sm text-gold">{member.effect}</p>
      <dl className="mt-3 grid grid-cols-2 gap-2 text-xs text-mist">
        <div><dt className="inline">Salary </dt><dd className="inline text-chalk">{formatMoney(member.salary)}</dd></div>
        <div>
          <dt className="inline">Contract </dt>
          <dd className="inline text-chalk">{left > 1 ? `${left} seasons, through ${member.contract_end}` : left === 1 ? `ends after ${member.contract_end}` : "expired"}</dd>
        </div>
        <div className="col-span-2"><dt className="sr-only">Career</dt><dd>{careerLine(member.career)}</dd></div>
      </dl>
    </article>
  );
}
