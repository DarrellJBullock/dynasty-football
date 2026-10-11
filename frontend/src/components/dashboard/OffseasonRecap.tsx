import Link from "next/link";
import { OvrBadge } from "@/components/ui/OvrBadge";
import { formatMoney } from "@/lib/format";
import type { OffseasonRecap as Recap, PlayerSummary, RecapMove, RecapSigning } from "@/lib/types";

/** What changed for the franchise between seasons; shown until the first game is played. */
export function OffseasonRecap({ recap }: { recap: Recap }) {
  const arrivals = recap.signed.length + recap.rookies.length;
  const losses = recap.retired.length + recap.departed.length;
  return (
    <section className="panel p-5" aria-label="Offseason recap">
      <div className="mb-4 flex flex-wrap items-baseline justify-between gap-2">
        <div>
          <div className="eyebrow text-gold">{recap.from_year} offseason</div>
          <h2 className="font-display text-2xl font-bold uppercase tracking-wide">
            Ready for {recap.year}
          </h2>
        </div>
        <p className="text-sm text-mist">
          {recap.re_signed.length} re-signed · {losses} gone · {arrivals} new
        </p>
      </div>
      <div className="grid gap-6 md:grid-cols-2 xl:grid-cols-4">
        <Column title="Re-signed" empty="No expiring contracts.">
          {recap.re_signed.map((s) => <SigningRow key={s.player.id} signing={s} />)}
        </Column>
        <Column title="New arrivals" empty="No new players.">
          {recap.signed.map((s) => <SigningRow key={s.player.id} signing={s} tag="FA" />)}
          {recap.rookies.map((p) => <PlayerRow key={p.id} player={p} note="Rookie" />)}
        </Column>
        <Column title="Gone" empty="Nobody left.">
          {recap.retired.map((p) => <PlayerRow key={p.id} player={p} note="Retired" />)}
          {recap.departed.map((p) => <PlayerRow key={p.id} player={p} note="Left in free agency" />)}
        </Column>
        <Column title="Development" empty="No rating changes.">
          {recap.risers.map((m) => <MoveRow key={m.player.id} move={m} />)}
          {recap.decliners.map((m) => <MoveRow key={m.player.id} move={m} />)}
        </Column>
      </div>
      {recap.league_retirements.length > 0 && (
        <p className="mt-5 border-t border-white/5 pt-4 text-sm text-mist">
          <span className="eyebrow mr-2">Around the league</span>
          {recap.league_retirements.map(({ player, team }, i) => (
            <span key={player.id}>
              {i > 0 && " · "}
              <Link href={`/players/${player.id}`} className="text-chalk hover:text-gold">
                {player.full_name}
              </Link>{" "}
              ({player.position}{team ? `, ${team.abbreviation}` : ""}) retired
            </span>
          ))}
        </p>
      )}
    </section>
  );
}

function Column({ title, empty, children }: { title: string; empty: string; children: React.ReactNode[] }) {
  const items = children.flat().filter(Boolean);
  return (
    <div role="group" aria-label={title}>
      <h3 className="eyebrow mb-2">{title}</h3>
      {items.length ? <ul className="space-y-1">{items}</ul> : <p className="text-sm text-mist">{empty}</p>}
    </div>
  );
}

function Name({ player }: { player: PlayerSummary }) {
  return (
    <Link href={`/players/${player.id}`} className="min-w-0 flex-1 truncate hover:text-gold">
      <span className="mr-1.5 text-xs text-mist">{player.position}</span>
      {player.full_name}
    </Link>
  );
}

function PlayerRow({ player, note }: { player: PlayerSummary; note: string }) {
  return (
    <li className="flex items-center gap-2 text-sm">
      <Name player={player} />
      <span className="text-xs text-mist">{note}</span>
      <OvrBadge value={player.overall} />
    </li>
  );
}

function SigningRow({ signing, tag }: { signing: RecapSigning; tag?: string }) {
  const { player, salary, years } = signing;
  return (
    <li className="flex items-center gap-2 text-sm">
      <Name player={player} />
      <span className="text-xs tabular-nums text-mist">
        {tag && `${tag} · `}{formatMoney(salary)} × {years}
      </span>
      <OvrBadge value={player.overall} />
    </li>
  );
}

function MoveRow({ move }: { move: RecapMove }) {
  const delta = move.after - move.before;
  return (
    <li className="flex items-center gap-2 text-sm">
      <Name player={move.player} />
      <span className="text-xs tabular-nums text-mist">{move.before} → {move.after}</span>
      <span className={`w-8 text-right text-xs font-semibold tabular-nums ${delta > 0 ? "text-emerald-300" : "text-rose-300"}`}>
        {delta > 0 ? `+${delta}` : delta}
      </span>
    </li>
  );
}
